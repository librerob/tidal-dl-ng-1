import json
import os
import pathlib
import random
import shutil
import tempfile
from collections.abc import Callable
from concurrent import futures
from functools import partial
from sqlite3 import Error as SQLiteError
from threading import BoundedSemaphore, Event, Lock
from uuid import uuid4

import m3u8
import requests
from ffmpeg import FFmpeg
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import HTTPError
from rich.progress import Progress, TaskID
from tidalapi import Album, Mix, Playlist, Session, Track, UserPlaylist, Video
from tidalapi.exceptions import TooManyRequests
from tidalapi.media import AudioExtensions, Codec, Quality, Stream, StreamManifest, VideoExtensions

from tidal_dl_ng.config import Settings
from tidal_dl_ng.constants import (
    CHUNK_SIZE,
    COVER_NAME,
    EXTENSION_LYRICS,
    PLAYLIST_EXTENSION,
    PLAYLIST_PREFIX,
    REQUESTS_TIMEOUT_SEC,
    MediaType,
    QualityVideo,
)
from tidal_dl_ng.helper.decryption import decrypt_file, decrypt_security_token
from tidal_dl_ng.helper.exceptions import MediaMissing
from tidal_dl_ng.helper.path import (
    check_media_exists,
    format_path_media,
    path_file_sanitize,
    sanitize_filename,
    url_to_filename,
)
from tidal_dl_ng.helper.tidal import (
    instantiate_media,
    items_results_all,
    name_builder_album_artist,
    name_builder_artist,
    name_builder_item,
    name_builder_title,
)
from tidal_dl_ng.metadata import Metadata
from tidal_dl_ng.model.downloader import DownloadSegmentResult
from tidal_dl_ng.model.gui_data import ProgressBars
from tidal_dl_ng.playlist_checkpoint import PlaylistCheckpoint
from tidal_dl_ng.rate_limit import DownloadStopped, RateLimit


# TODO: Set appropriate client string and use it for video download.
# https://github.com/globocom/m3u8#using-different-http-clients
class RequestsClient:
    def download(
        self, uri: str, timeout: int = REQUESTS_TIMEOUT_SEC, headers: dict | None = None, verify_ssl: bool = True
    ):
        if not headers:
            headers = {}

        o = requests.get(uri, timeout=timeout, headers=headers)

        return o.text, o.url


# TODO: Use pathlib.Path everywhere
class Download:
    settings: Settings
    session: Session
    skip_existing: bool = False
    fn_logger: Callable
    progress_gui: ProgressBars
    progress: Progress
    progress_overall: Progress
    event_abort: Event
    event_run: Event

    def __init__(
        self,
        session: Session,
        path_base: str,
        fn_logger: Callable,
        skip_existing: bool = False,
        progress_gui: ProgressBars = None,
        progress: Progress = None,
        progress_overall: Progress = None,
        event_abort: Event = None,
        event_run: Event = None,
    ):
        self.settings = Settings()
        self.session = session
        self.skip_existing = skip_existing
        self.fn_logger = fn_logger
        self.progress_gui = progress_gui
        self.progress = progress
        self.progress_overall = progress_overall
        self.path_base = path_base
        self.event_abort = event_abort if event_abort is not None else Event()
        self.rate_limit = RateLimit(self.event_abort, self.settings.data)
        self.results_lock = Lock()
        self.quality_lock = Lock()
        self.transfer_slots = BoundedSemaphore(4)
        self.counts = dict.fromkeys(("downloaded", "skipped_existing", "rate_limited", "unavailable", "other"), 0)
        self.failures = []
        self.event_run = event_run if event_run is not None else Event()
        if event_run is None:
            self.event_run.set()

        if not self.settings.data.path_binary_ffmpeg and (
            self.settings.data.video_convert_mp4 or self.settings.data.extract_flac
        ):
            self.settings.data.video_convert_mp4 = False
            self.settings.data.extract_flac = False

            self.fn_logger.error(
                "FFmpeg path is not set. Videos can be downloaded but will not be processed. FLAC cannot be "
                "extracted from MP4 containers. Make sure FFmpeg is installed. The path to the FFmpeg binary must "
                "be set in (`path_binary_ffmpeg`)."
            )

    def _download(
        self,
        media: Track | Video,
        path_file: pathlib.Path,
        stream_manifest: StreamManifest | None = None,
        quality_video: QualityVideo | None = None,
    ) -> (bool, pathlib.Path):
        if self.event_abort.is_set():
            return False, path_file
        media_name: str = name_builder_item(media)
        urls: [str]
        path_base: pathlib.Path = path_file.parent
        result_segments: bool = True
        dl_segment_results: [DownloadSegmentResult] = []
        result_merge: bool = False

        # Get urls for media.
        try:
            if isinstance(media, Track):
                urls = stream_manifest.get_urls()
            elif isinstance(media, Video):
                m3u8_variant: m3u8.M3U8 = m3u8.load(media.get_url())
                # Find the desired video resolution or the next best one.
                m3u8_playlist, codecs = self._extract_video_stream(m3u8_variant, int(quality_video if quality_video is not None else self.settings.data.quality_video))
                # Populate urls.
                urls = m3u8_playlist.files
        except Exception:
            return False, path_file

        # Set the correct progress output channel.
        if self.progress_gui is None:
            progress_to_stdout: bool = True
        else:
            progress_to_stdout: bool = False
            # Send signal to GUI with media name
            self.progress_gui.item_name.emit(media_name[:30])

        # Compute total iterations for progress
        urls_count: int = len(urls)

        if not urls_count:
            return False, path_file
        progress_total = urls_count if urls_count > 1 else None
        block_size = 1048576 if urls_count == 1 else None

        # Create progress Task
        p_task: TaskID = self.progress.add_task(
            f"[blue]Item '{media_name[:30]}'",
            total=progress_total,
            visible=progress_to_stdout,
        )

        with futures.ThreadPoolExecutor(
            max_workers=max(1, min(4, self.settings.data.downloads_simultaneous_per_track_max))
        ) as executor:
            # Dispatch all download tasks to worker threads
            l_futures: [futures.Future] = [
                executor.submit(self._download_segment, url, path_base, block_size, p_task, progress_to_stdout)
                for url in urls
            ]

            # Report results as they become available
            for future in futures.as_completed(l_futures):
                # Retrieve result
                result_dl_segment: DownloadSegmentResult = future.result()

                dl_segment_results.append(result_dl_segment)

                # check for a link that was skipped
                if not result_dl_segment.result and (urls_count == 1 or result_dl_segment.url != urls[-1]):
                    # Sometimes it happens, if a track is very short (< 8 seconds or so), that the last URL in `urls` is
                    # invalid (HTTP Error 500) and not necessary. File won't be corrupt.
                    # If this is NOT the case, but any other URL has resulted in an error,
                    # mark the whole thing as corrupt.
                    result_segments = False
                    self.fn_logger.error(f"Something went wrong while downloading {media_name}. File is corrupt!")

                # If app is terminated (CTRL+C)
                if self.event_abort.is_set() or self.rate_limit.open:
                    # Cancel all not yet started tasks
                    for f in l_futures:
                        f.cancel()

                    return False, path_file

        if self.event_abort.is_set():
            return False, path_file
        if urls_count == 1 and result_segments:
            self.progress.update(p_task, total=self.progress.tasks[p_task].completed)
        tmp_path_file_decrypted: pathlib.Path = path_file

        # Only if no error happened while downloading.
        if result_segments:
            # Bring list into right order, so segments can be easily merged.
            dl_segment_results.sort(key=lambda x: x.id_segment)
            result_merge: bool = self._segments_merge(path_file, dl_segment_results)

            if not result_merge:
                self.fn_logger.error(f"Something went wrong while writing to {media_name}. File is corrupt!")
            elif result_merge and isinstance(media, Track) and stream_manifest.is_encrypted:
                key, nonce = decrypt_security_token(stream_manifest.encryption_key)
                tmp_path_file_decrypted = path_file.with_suffix(".decrypted")
                decrypt_file(path_file, tmp_path_file_decrypted, key, nonce)

        return result_merge, tmp_path_file_decrypted

    def _segments_merge(self, path_file, dl_segment_results) -> bool:
        result: bool = True

        # Copy the content of all segments into one file.
        try:
            with path_file.open("wb") as f_target:
                for dl_segment_result in dl_segment_results:
                    with dl_segment_result.path_segment.open("rb") as f_segment:
                        # Read and write junks, which gives better HDD write performance
                        while segment := f_segment.read(CHUNK_SIZE):
                            f_target.write(segment)

                    # Delete segment from HDD
                    dl_segment_result.path_segment.unlink()

        except Exception:
            if dl_segment_result is not dl_segment_results[-1]:
                result = False

        return result

    def _download_segment(
        self, url: str, path_base: pathlib.Path, block_size: int | None, p_task: TaskID, progress_to_stdout: bool
    ) -> DownloadSegmentResult:
        result: bool = False
        path_segment: pathlib.Path = path_base / url_to_filename(url)
        # Calculate the segment ID based on the file name within the URL.
        filename_stem: str = str(path_segment.stem).split("_")[-1]
        # CAUTION: This is a workaround, so BTS (LOW quality) track will work. They usually have only ONE link.
        id_segment: int = int(filename_stem) if filename_stem.isdecimal() else 0
        error: HTTPError | None = None

        # If app is terminated (CTRL+C)
        if self.event_abort.is_set():
            return DownloadSegmentResult(
                result=False, url=url, path_segment=path_segment, id_segment=id_segment, error=error
            )

        if not self.event_run.is_set():
            self.event_run.wait()

        with self.transfer_slots:
            try:
                self.rate_limit.wait()
                with requests.Session() as session:
                    session.mount("https://", HTTPAdapter(max_retries=Retry(total=2, backoff_factor=1)))
                    with session.get(url, stream=True, timeout=REQUESTS_TIMEOUT_SEC) as response:
                        response.raise_for_status()
                        with path_segment.open("wb") as stream:
                            for data in response.iter_content(chunk_size=block_size):
                                if self.event_abort.is_set():
                                    raise DownloadStopped
                                stream.write(data)
                                self.progress.advance(p_task)
                result = True
            except HTTPError as exc:
                error = exc
                self.progress.advance(p_task)
            except (DownloadStopped, requests.RequestException, OSError):
                self.progress.advance(p_task)

        # To send the progress to the GUI, we need to emit the percentage.
        if not progress_to_stdout:
            self.progress_gui.item.emit(self.progress.tasks[p_task].percentage)

        return DownloadSegmentResult(
            result=result, url=url, path_segment=path_segment, id_segment=id_segment, error=error
        )

    def extension_guess(
        self, quality_audio: Quality, metadata_tags: [str], is_video: bool
    ) -> AudioExtensions | VideoExtensions:
        result: AudioExtensions | VideoExtensions

        if is_video:
            result = AudioExtensions.MP4 if self.settings.data.video_convert_mp4 else VideoExtensions.TS
        else:
            result = (
                AudioExtensions.FLAC
                if (
                    self.settings.data.extract_flac
                    and quality_audio in (Quality.hi_res_lossless, Quality.high_lossless)
                )
                or ("HIRES_LOSSLESS" not in metadata_tags and quality_audio not in (Quality.low_96k, Quality.low_320k))
                or quality_audio == Quality.high_lossless
                else AudioExtensions.M4A
            )

        return result

    def _record(self, status, media=None, media_id=None, playlist=None, media_type=None):
        with self.results_lock:
            self.counts[status] += 1
            if status in {"rate_limited", "unavailable", "other"}:
                artist = getattr(media, "artist", None)
                self.failures.append({
                    "track_id": str(getattr(media, "id", media_id) or ""),
                    "media_type": "video" if isinstance(media, Video) or media_type == MediaType.VIDEO else "track" if isinstance(media, Track) or media_type == MediaType.TRACK else None,
                    "title": getattr(media, "name", ""),
                    "artist": getattr(artist, "name", ""),
                    "playlist": playlist,
                    "reason": status,
                })

    def report(self):
        with self.results_lock:
            counts = self.counts.copy()
            failures = self.failures.copy()
            self.counts = dict.fromkeys(counts, 0)
            self.failures.clear()
        failed = sum(counts[reason] for reason in ("rate_limited", "unavailable", "other"))
        if counts["downloaded"] or counts["skipped_existing"] or failed:
            self.fn_logger.info(
                f'Downloaded {counts["downloaded"]}, skipped existing {counts["skipped_existing"]}, failed {failed} '
                f'(rate_limited {counts["rate_limited"]}, unavailable {counts["unavailable"]}, other {counts["other"]}).'
            )
        if failures:
            base = pathlib.Path(self.path_base).expanduser()
            destination = base / "failed_tracks.json"
            try:
                base.mkdir(parents=True, exist_ok=True)
                old = json.loads(destination.read_text(encoding="utf-8")) if destination.exists() else []
                if not isinstance(old, list):
                    msg = "Invalid failed-track report"
                    raise TypeError(msg)  # noqa: TRY301
                with tempfile.TemporaryDirectory(dir=base) as directory:
                    temporary = pathlib.Path(directory) / destination.name
                    temporary.write_text(json.dumps(old + failures, ensure_ascii=False, indent=2), encoding="utf-8")
                    temporary.replace(destination)
            except (OSError, TypeError, ValueError):
                with self.results_lock:
                    self.failures[:0] = failures
                self.fn_logger.warning("Could not update failed_tracks.json.")

    def item(
        self,
        file_template: str,
        media: Track | Video = None,
        media_id: str = None,
        media_type: MediaType = None,
        video_download: bool = True,
        download_delay: bool = False,
        quality_audio: Quality | None = None,
        quality_video: QualityVideo | None = None,
        is_parent_album: bool = False,
        repair: bool = False,
        playlist: str | None = None,
    ) -> tuple[bool, pathlib.Path | str]:
        try:
            self.rate_limit.wait()
            if isinstance(media, Track) and not media.available:
                self._record("unavailable", media, media_id, playlist, media_type)
                return False, ""
            status, path = self._item(
                file_template, media, media_id, media_type, video_download, download_delay,
                quality_audio, quality_video, is_parent_album, repair,
            )
        except DownloadStopped:
            if playlist is not None:
                raise
            return False, ""
        except TooManyRequests:
            self._record("rate_limited", media, media_id, playlist, media_type)
            return False, ""
        except Exception:
            self.fn_logger.exception("Could not download item.")
            self._record("other", media, media_id, playlist, media_type)
            return False, ""
        self._record("downloaded" if status else "skipped_existing" if path else "other", media, media_id, playlist, media_type)
        return status, path

    def _item(
        self,
        file_template: str,
        media: Track | Video = None,
        media_id: str = None,
        media_type: MediaType = None,
        video_download: bool = True,
        download_delay: bool = False,
        quality_audio: Quality | None = None,
        quality_video: QualityVideo | None = None,
        is_parent_album: bool = False,
        repair: bool = False,
    ) -> (bool, pathlib.Path):
        try:
            if media_id and media_type:
                # If no media instance is provided, we need to create the media instance.
                media = self.rate_limit.call(lambda: instantiate_media(self.session, media_type, media_id))
            elif isinstance(media, Track):  # Check if media is available not deactivated / removed from TIDAL.
                if not media.available:
                    self.fn_logger.info(
                        f"This track is not available for listening anymore on TIDAL. Skipping: {name_builder_item(media)}"
                    )

                    return False, ""
                else:
                    # Re-create media instance with full album information
                    media = self.rate_limit.call(lambda: self.session.track(media.id, with_album=True))
            elif not media:
                return False, ""
        except (TooManyRequests, DownloadStopped):
            raise
        except Exception:
            return False, ""

        # If video download is not allowed end here
        if not video_download and isinstance(media, Video):
            self.fn_logger.info(
                f"Video downloads are deactivated (see settings). Skipping video: {name_builder_item(media)}"
            )

            return False, ""

        # Create file name and path
        file_extension_dummy: str = self.extension_guess(
            quality_audio,
            metadata_tags=[] if isinstance(media, Video) else media.media_metadata_tags,
            is_video=isinstance(media, Video),
        )
        file_name_relative: str = format_path_media(file_template, media, self.settings.data.album_track_num_pad_min)
        path_media_dst: pathlib.Path = (
            pathlib.Path(self.path_base).expanduser() / (file_name_relative + file_extension_dummy)
        ).absolute()

        # Sanitize final path_file to fit into OS boundaries.
        path_media_dst = pathlib.Path(path_file_sanitize(path_media_dst, adapt=True))

        # Compute if and how downloads need to be skipped.
        skip_download: bool = False

        if self.skip_existing and not repair:
            skip_file: bool = check_media_exists(path_media_dst)

            if self.settings.data.symlink_to_track and not isinstance(media, Video):
                # Compute symlink tracks path, sanitize and check if file exists
                file_name_track_dir_relative: str = format_path_media(self.settings.data.format_track, media)
                path_media_track_dir: pathlib.Path = (
                    pathlib.Path(self.path_base).expanduser() / (file_name_track_dir_relative + file_extension_dummy)
                ).absolute()
                path_media_track_dir = pathlib.Path(path_file_sanitize(path_media_track_dir, adapt=True))
                file_exists_track_dir: bool = check_media_exists(path_media_track_dir)
                file_exists_playlist_dir: bool = (
                    not file_exists_track_dir and skip_file and not path_media_dst.is_symlink()
                )
                skip_download = file_exists_playlist_dir or file_exists_track_dir

                # If
                if skip_file and file_exists_playlist_dir:
                    skip_file = False
        else:
            skip_file: bool = False

        result_download = False
        if not skip_file:
            do_flac_extract = False
            # Get extension.
            file_extension: str
            stream_manifest: StreamManifest | None = None

            if isinstance(media, Track):
                media_stream: Stream = self.rate_limit.call(partial(self._track_stream, media, quality_audio))
                stream_manifest = media_stream.get_stream_manifest()

                file_extension = stream_manifest.file_extension

                if self.settings.data.extract_flac and (
                    stream_manifest.codecs.upper() == Codec.FLAC and file_extension != AudioExtensions.FLAC
                ):
                    file_extension = AudioExtensions.FLAC
                    do_flac_extract = True
            elif isinstance(media, Video):
                file_extension = AudioExtensions.MP4 if self.settings.data.video_convert_mp4 else VideoExtensions.TS

            # Compute file name, sanitize once again and create destination directory
            path_media_dst = path_media_dst.with_suffix(file_extension)
            path_media_dst = pathlib.Path(path_file_sanitize(path_media_dst, adapt=True))
            os.makedirs(path_media_dst.parent, exist_ok=True)

            if not skip_download:
                # Create a temp directory and file.
                with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_path_dir:
                    tmp_path_file: pathlib.Path = pathlib.Path(tmp_path_dir) / str(uuid4())

                    # Create empty file
                    tmp_path_file.touch()

                    # Download media.
                    result_download, tmp_path_file = self._download(
                        media=media, stream_manifest=stream_manifest, path_file=tmp_path_file, quality_video=quality_video
                    )

                    if result_download:
                        # Convert video from TS to MP4
                        if isinstance(media, Video) and self.settings.data.video_convert_mp4:
                            # Convert `*.ts` file to `*.mp4` using ffmpeg
                            tmp_path_file = self._video_convert(tmp_path_file)

                        # Extract FLAC from MP4 container using ffmpeg
                        if isinstance(media, Track) and self.settings.data.extract_flac and do_flac_extract:
                            tmp_path_file = self._extract_flac(tmp_path_file)

                        tmp_path_lyrics: pathlib.Path | None = None
                        tmp_path_cover: pathlib.Path | None = None

                        # Write metadata to file.
                        if not isinstance(media, Video):
                            result_metadata, tmp_path_lyrics, tmp_path_cover = self.metadata_write(
                                media, tmp_path_file, is_parent_album, media_stream
                            )

                        # Move lyrics file
                        if self.settings.data.lyrics_file and not isinstance(media, Video) and tmp_path_lyrics:
                            self._move_lyrics(tmp_path_lyrics, path_media_dst)

                        # Move cover file
                        # TODO: Cover is downloaded with every track of the album. Needs refactoring, so cover is only
                        #  downloaded for an album once.
                        if self.settings.data.cover_album_file and tmp_path_cover:
                            self._move_cover(tmp_path_cover, path_media_dst)

                        # Move final file to the configured destination directory.
                        if self.event_abort.is_set() or tmp_path_file.stat().st_size == 0:
                            result_download = False
                        else:
                            with tempfile.NamedTemporaryFile(
                                prefix=".tdn-", suffix=".part", dir=path_media_dst.parent, delete=False
                            ) as staging_file:
                                staging_path = pathlib.Path(staging_file.name)
                            try:
                                shutil.copyfile(tmp_path_file, staging_path)
                                if self.event_abort.is_set():
                                    result_download = False
                                else:
                                    staging_path.replace(path_media_dst)
                                    self.fn_logger.info(f"Downloaded item '{name_builder_item(media)}'.")
                            finally:
                                staging_path.unlink(missing_ok=True)

            # If files needs to be symlinked, do postprocessing here.
            if (skip_download or result_download) and self.settings.data.symlink_to_track and not isinstance(media, Video):
                path_media_track_dir: pathlib.Path = self.media_move_and_symlink(media, path_media_dst, file_extension)

        else:
            self.fn_logger.debug(f"Download skipped, since file exists: '{path_media_dst}'")

        status_download = result_download

        # Whether a file was downloaded or skipped and the download delay is enabled, wait until the next download.
        # Only use this, if you have a list of several Track items.
        if (download_delay and not skip_file) and not self.event_abort.is_set():
            time_sleep: float = round(
                random.SystemRandom().uniform(
                    self.settings.data.download_delay_sec_min, self.settings.data.download_delay_sec_max
                ),
                1,
            )

            self.fn_logger.debug(f"Next download will start in {time_sleep} seconds.")
            self.event_abort.wait(time_sleep)

        return status_download, path_media_dst if skip_file or skip_download or result_download else ""

    def media_move_and_symlink(
        self, media: Track | Video, path_media_src: pathlib.Path, file_extension: str
    ) -> pathlib.Path:
        # Compute tracks path, sanitize and ensure path exists
        file_name_relative: str = format_path_media(self.settings.data.format_track, media)
        path_media_dst: pathlib.Path = (
            pathlib.Path(self.path_base).expanduser() / (file_name_relative + file_extension)
        ).absolute()
        path_media_dst = pathlib.Path(path_file_sanitize(path_media_dst, adapt=True))

        os.makedirs(path_media_dst.parent, exist_ok=True)

        # Move item and symlink it
        if path_media_dst != path_media_src:
            if self.skip_existing:
                skip_file: bool = check_media_exists(path_media_dst)
                skip_symlink: bool = path_media_src.is_symlink()
            else:
                skip_file: bool = False
                skip_symlink: bool = False

            if not skip_file:
                self.fn_logger.debug(f"Move: {path_media_src} -> {path_media_dst}")
                shutil.move(path_media_src, path_media_dst)

            if not skip_symlink:
                self.fn_logger.debug(f"Symlink: {path_media_src} -> {path_media_dst}")
                path_media_dst_relative: pathlib.Path = path_media_dst.relative_to(path_media_src.parent, walk_up=True)

                path_media_src.unlink(missing_ok=True)
                path_media_src.symlink_to(path_media_dst_relative)

        return path_media_dst

    def _track_stream(self, media: Track, quality: Quality | None):
        with self.quality_lock:
            old_quality = self.session.audio_quality
            try:
                if quality is not None:
                    self.session.audio_quality = quality
                return media.get_stream()
            finally:
                self.session.audio_quality = old_quality

    def adjust_quality_audio(self, quality) -> Quality:
        # Save original quality settings
        quality_old: Quality = self.session.audio_quality
        self.session.audio_quality = quality

        return quality_old

    def adjust_quality_video(self, quality) -> QualityVideo:
        quality_old: QualityVideo = self.settings.data.quality_video

        self.settings.data.quality_video = quality

        return quality_old

    def _move_file(self, path_file_source: pathlib.Path, path_file_destination: str | pathlib.Path) -> bool:
        result: bool

        # Check if the file was downloaded
        if path_file_source and path_file_source.is_file():
            # Move it.
            shutil.move(path_file_source, path_file_destination)

            result = True
        else:
            result = False

        return result

    def _move_lyrics(self, path_lyrics: pathlib.Path, file_media_dst: pathlib.Path) -> bool:
        # Build tmp lyrics filename
        path_file_lyrics: pathlib.Path = file_media_dst.with_suffix(EXTENSION_LYRICS)
        result: bool = self._move_file(path_lyrics, path_file_lyrics)

        return result

    def _move_cover(self, path_cover: pathlib.Path, file_media_dst: pathlib.Path) -> bool:
        # Build tmp lyrics filename
        path_file_cover: pathlib.Path = file_media_dst.parent / COVER_NAME
        result: bool = self._move_file(path_cover, path_file_cover)

        return result

    def lyrics_to_file(self, dir_destination: pathlib.Path, lyrics: str) -> str:
        return self.write_to_tmp_file(dir_destination, mode="x", content=lyrics)

    def cover_to_file(self, dir_destination: pathlib.Path, image: bytes) -> str:
        return self.write_to_tmp_file(dir_destination, mode="xb", content=image)

    def write_to_tmp_file(self, dir_destination: pathlib.Path, mode: str, content: str | bytes) -> str:
        result: pathlib.Path = dir_destination / str(uuid4())
        encoding: str | None = "utf-8" if isinstance(content, str) else None

        try:
            with open(result, mode=mode, encoding=encoding) as f:
                f.write(content)
        except:
            result = ""

        return result

    @staticmethod
    def cover_data(url: str = None, path_file: str = None) -> str | bytes:
        result: str | bytes = ""

        if url:
            try:
                response: requests.Response = requests.get(url, timeout=REQUESTS_TIMEOUT_SEC)
                result = response.content
            except Exception as e:
                # TODO: Implement propper logging.
                print(e)
            finally:
                response.close()
        elif path_file:
            try:
                with open(path_file, "rb") as f:
                    result = f.read()
            except OSError as e:
                # TODO: Implement propper logging.
                print(e)

        return result

    def metadata_write(
        self, track: Track, path_media: pathlib.Path, is_parent_album: bool, media_stream: Stream
    ) -> (bool, pathlib.Path | None, pathlib.Path | None):
        result: bool = False
        path_lyrics: pathlib.Path | None = None
        path_cover: pathlib.Path | None = None
        release_date: str = (
            track.album.available_release_date.strftime("%Y-%m-%d")
            if track.album.available_release_date
            else track.album.release_date.strftime("%Y-%m-%d") if track.album.release_date else ""
        )
        copy_right: str = track.copyright if hasattr(track, "copyright") and track.copyright else ""
        isrc: str = track.isrc if hasattr(track, "isrc") and track.isrc else ""
        lyrics: str = ""
        cover_data: bytes = None

        if self.settings.data.lyrics_embed or self.settings.data.lyrics_file:
            # Try to retrieve lyrics.
            try:
                lyrics_obj = track.lyrics()

                if lyrics_obj.subtitles:
                    lyrics = lyrics_obj.subtitles
                elif lyrics_obj.text:
                    lyrics = lyrics_obj.text
            except:
                lyrics = ""
                # TODO: Implement proper logging.
                print(f"Could not retrieve lyrics for `{name_builder_item(track)}`.")

        if lyrics and self.settings.data.lyrics_file:
            path_lyrics = self.lyrics_to_file(path_media.parent, lyrics)

        if self.settings.data.metadata_cover_embed or (self.settings.data.cover_album_file and is_parent_album):
            url_cover = track.album.image(int(self.settings.data.metadata_cover_dimension))
            cover_data = self.cover_data(url=url_cover)

        if cover_data and self.settings.data.cover_album_file and is_parent_album:
            path_cover = self.cover_to_file(path_media.parent, cover_data)

        # `None` values are not allowed.
        m: Metadata = Metadata(
            path_file=path_media,
            lyrics=lyrics,
            copy_right=copy_right,
            title=name_builder_title(track),
            artists=name_builder_artist(track),
            album=track.album.name if track.album else "",
            tracknumber=track.track_num,
            date=release_date,
            isrc=isrc,
            albumartist=name_builder_album_artist(track),
            totaltrack=track.album.num_tracks if track.album and track.album.num_tracks else 1,
            totaldisc=track.album.num_volumes if track.album and track.album.num_volumes else 1,
            discnumber=track.volume_num if track.volume_num else 1,
            cover_data=cover_data if self.settings.data.metadata_cover_embed else None,
            album_replay_gain=media_stream.album_replay_gain,
            album_peak_amplitude=media_stream.album_peak_amplitude,
            track_replay_gain=media_stream.track_replay_gain,
            track_peak_amplitude=media_stream.track_peak_amplitude,
            url_share=track.share_url if track.share_url else "",
            replay_gain_write=self.settings.data.metadata_replay_gain,
        )

        m.save()

        result = True

        return result, path_lyrics, path_cover

    def items(
        self,
        file_template: str,
        media: Album | Playlist | UserPlaylist | Mix = None,
        media_id: str = None,
        media_type: MediaType = None,
        video_download: bool = False,
        download_delay: bool = True,
        quality_audio: Quality | None = None,
        quality_video: QualityVideo | None = None,
    ):
        # If no media instance is provided, we need to create the media instance.
        if media_id and media_type:
            try:
                media = self.rate_limit.call(lambda: instantiate_media(self.session, media_type, media_id))
            except (DownloadStopped, TooManyRequests):
                return
        elif not media:
            raise MediaMissing

        # Create file name and path
        file_name_relative: str = format_path_media(file_template, media, self.settings.data.album_track_num_pad_min)

        # Get the name of the list and check, if videos should be included.
        list_media_name: str = name_builder_title(media)
        list_media_name_short: str = list_media_name[:30]

        # Get all items of the list.
        try:
            items = self.rate_limit.call(lambda: items_results_all(media, videos_include=video_download))
        except (DownloadStopped, TooManyRequests):
            return

        # Determine where to redirect the progress information.
        if self.progress_gui is None:
            progress_stdout: bool = True
        else:
            progress_stdout: bool = False
            self.progress_gui.list_name.emit(list_media_name_short)

        progress: Progress = self.progress_overall if self.progress_overall else self.progress

        # Create the list progress task.
        p_task1: TaskID = progress.add_task(
            f"[green]List '{list_media_name_short}'", total=len(items), visible=progress_stdout
        )

        is_album: bool = isinstance(media, Album)
        result_paths = {}
        quality_audio = quality_audio or self.settings.data.quality_audio
        quality_video = quality_video if quality_video is not None else self.settings.data.quality_video
        checkpoint = None
        try:
            checkpoint = PlaylistCheckpoint(
                pathlib.Path(self.path_base).expanduser(),
                [type(media).__name__, str(media.id), file_name_relative,
                 str(quality_audio or self.settings.data.quality_audio),
                 str(quality_video or self.settings.data.quality_video)],
                [f"{type(track).__name__}:{track.id}" for track in items],
            )
        except (SQLiteError, OSError):
            self.fn_logger.warning("Playlist checkpoint unavailable. Continuing without saved progress.")

        completed = self._run_playlist(
            items, progress, p_task1, result_paths, progress_stdout,
            media_options=dict(
                file_template=file_name_relative,
                quality_audio=quality_audio,
                quality_video=quality_video,
                download_delay=download_delay,
                is_parent_album=is_album,
                playlist=list_media_name,
            ),
            checkpoint=checkpoint,
        )
        if self.event_abort.is_set():
            return
        if self.rate_limit.open:
            self.fn_logger.warning(
                f"Paused list '{list_media_name}' after processing {completed} of {len(items)} tracks. "
                f"{len(items) - completed} tracks still pending."
            )
            return

        # Create playlist file
        if self.settings.data.playlist_create:
            self.playlist_populate([result_paths[index] for index in sorted(result_paths)], list_media_name)

        self.fn_logger.info(f"Finished list '{list_media_name}'.")

    def _run_playlist(self, items, progress, task, result_paths, progress_stdout, media_options, checkpoint=None):
        repair_positions = set()
        if checkpoint is not None:
            try:
                saved = checkpoint.completed()
                repair_positions = checkpoint.recorded_positions() - saved.keys()
                result_paths.update(saved)
            except (SQLiteError, OSError):
                self.fn_logger.warning("Playlist checkpoint unavailable. Continuing without saved progress.")
                checkpoint = None
        completed = len(result_paths)
        progress.advance(task, completed)
        remaining = ((index, track) for index, track in enumerate(items) if index not in result_paths)
        pending = {}
        workers = max(1, self.settings.data.downloads_concurrent_max)
        with futures.ThreadPoolExecutor(max_workers=workers) as executor:
            while True:
                if self.event_abort.is_set() or self.rate_limit.open:
                    for future in pending:
                        future.cancel()
                else:
                    while len(pending) < workers and not (self.event_abort.is_set() or self.rate_limit.open):
                        entry = next(remaining, None)
                        if entry is None:
                            break
                        index, track = entry
                        options = {**media_options, "repair": True} if index in repair_positions else media_options
                        pending[executor.submit(self.item, media=track, **options)] = index
                if not pending:
                    break

                finished, _ = futures.wait(pending, return_when=futures.FIRST_COMPLETED)
                for future in finished:
                    index = pending.pop(future)
                    try:
                        _, path = future.result()
                    except (DownloadStopped, futures.CancelledError):
                        continue
                    if path:
                        result_paths[index] = path
                        if checkpoint is not None:
                            try:
                                checkpoint.record(index, path)
                            except (SQLiteError, OSError):
                                self.fn_logger.warning("Could not save playlist progress. Continuing the download.")
                                checkpoint = None
                    completed += 1
                    progress.advance(task)
                    if not progress_stdout:
                        self.progress_gui.list_item.emit(progress.tasks[task].percentage)

        return completed

    def playlist_populate(self, paths: list[pathlib.Path], name_list: str) -> list[pathlib.Path]:
        by_directory = {}
        for path in paths:
            if path.suffix.lower() in {str(extension) for extension in AudioExtensions}:
                by_directory.setdefault(path.parent, []).append(path)
        result = []
        for directory, tracks in by_directory.items():
            destination = pathlib.Path(path_file_sanitize(
                directory / sanitize_filename(PLAYLIST_PREFIX + name_list + PLAYLIST_EXTENSION), adapt=True,
            ))
            with destination.open("w", encoding="utf-8") as stream:
                for track in tracks:
                    target = track.resolve() if track.is_symlink() else track
                    stream.write(str(target.relative_to(destination.parent, walk_up=True)) + "\n")
            result.append(destination)
        return result

    def _video_convert(self, path_file: pathlib.Path) -> pathlib.Path:
        path_file_out: pathlib.Path = path_file.with_suffix(AudioExtensions.MP4)
        ffmpeg = (
            FFmpeg(executable=self.settings.data.path_binary_ffmpeg)
            .option("y")
            .input(url=path_file)
            .output(url=path_file_out, codec="copy", map=0, loglevel="quiet")
        )

        ffmpeg.execute()

        return path_file_out

    def _extract_flac(self, path_media_src: pathlib.Path) -> pathlib.Path:
        path_media_out = path_media_src.with_suffix(AudioExtensions.FLAC)
        ffmpeg = (
            FFmpeg(executable=self.settings.data.path_binary_ffmpeg)
            .input(url=path_media_src)
            .output(
                url=path_media_out,
                map=0,
                movflags="use_metadata_tags",
                acodec="copy",
                map_metadata="0:g",
                loglevel="quiet",
            )
        )

        ffmpeg.execute()

        return path_media_out

    def _extract_video_stream(self, m3u8_variant: m3u8.M3U8, quality: int) -> (m3u8.M3U8 | bool, str):
        m3u8_playlist: m3u8.M3U8 | bool = False
        resolution_best: int = 0
        mime_type: str = ""

        if m3u8_variant.is_variant:
            for playlist in m3u8_variant.playlists:
                if resolution_best < playlist.stream_info.resolution[1]:
                    resolution_best = playlist.stream_info.resolution[1]
                    m3u8_playlist = m3u8.load(playlist.uri)
                    mime_type = playlist.stream_info.codecs

                    if quality == playlist.stream_info.resolution[1]:
                        break

        return m3u8_playlist, mime_type
