import dataclasses

from randovania.game_description.db.node import Node, NodeContext
from randovania.game_description.resources.resource_info import ResourceGain, ResourceInfo


@dataclasses.dataclass(frozen=True, slots=True)
class ResourceNode(Node):
    @property
    def is_resource_node(self) -> bool:
        return True

    def resource(self, context: NodeContext) -> ResourceInfo:
        raise NotImplementedError

    def can_collect(self, context: NodeContext) -> bool:
        raise NotImplementedError

    def is_collected(self, context: NodeContext) -> bool:
        raise NotImplementedError

    def resource_gain_on_collect(self, context: NodeContext) -> ResourceGain:
        raise NotImplementedError
