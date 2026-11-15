from types import SimpleNamespace
from unittest.mock import Mock

from PySide6 import QtWidgets

from tidal_dl_ng.dialog import DialogPreferences
from tidal_dl_ng.model.cfg import Settings


def test_preferences_opens_and_saves_update_checkbox():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    settings = SimpleNamespace(data=Settings())
    saved = Mock()
    dialog = DialogPreferences(settings=settings, settings_save=saved)
    dialog.show()
    try:
        app.processEvents()
        assert dialog.isVisible()
        assert dialog.ui.cb_check_for_updates.isChecked()
        dialog.ui.cb_check_for_updates.setChecked(False)
        dialog.accept()
        assert settings.data.check_for_updates is False
        saved.emit.assert_called_once_with()
    finally:
        dialog.close()
