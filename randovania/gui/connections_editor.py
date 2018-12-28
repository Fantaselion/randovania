from typing import Optional

from PySide2.QtWidgets import QDialog, QWidget

from randovania.game_description.requirements import RequirementSet
from randovania.game_description.resources import ResourceDatabase
from randovania.gui.connections_editor_ui import Ui_ConnectionEditor
from randovania.gui.connections_visualizer import ConnectionsVisualizer


class ConnectionsEditor(QDialog, Ui_ConnectionEditor):
    def __init__(self, parent: QWidget, resource_database: ResourceDatabase, requirement_set: Optional[RequirementSet]):
        super().__init__(parent)
        self.setupUi(self)

        self._connections_visualizer = ConnectionsVisualizer(
            self.visualizer_contents,
            self.gridLayout,
            resource_database,
            requirement_set,
            True,
            num_columns_for_alternatives=1
        )

