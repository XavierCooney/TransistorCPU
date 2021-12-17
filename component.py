import abc
import typing as typ


class Node:
    def __init__(self, component: 'Component', name: str):
        self.component = component
        self.name = name
        self.connected_to: typ.List['Node'] = []

    def get_path(self) -> str:
        return f'{self.component.get_path()}>{self.name}'

    def __repr__(self) -> str:
        return f'[Node @ {self.get_path()}]'


class Component(abc.ABC):
    @property
    @abc.abstractproperty
    def node_names(self) -> typ.List[str]: pass

    @property
    @abc.abstractproperty
    def component_name(self) -> str: pass

    def __init__(self, parent: typ.Optional['Component'], role: str) -> None:
        self.sub_components: typ.Dict[str, 'Component'] = {}
        self.nodes: typ.Dict[str, Node] = {}
        self.parent = parent
        self.role = role

        assert len(self.node_names) == len(set(self.node_names))
        for node_name in self.node_names:
            self.nodes[node_name] = Node(self, node_name)

        self.build()

    @abc.abstractmethod
    def build(self) -> None: pass

    def add_component(self, component: 'Component') -> 'Component':
        assert component.role not in self.sub_components
        self.sub_components[component.role] = component

        return component

    def get_path(self) -> str:
        prefix = self.parent.get_path() + '.' if self.parent else ''
        return f'{prefix}{self.role}[{self.component_name}]'

    def connect(self, from_name: str, to_node: Node) -> None:
        assert from_name in self.nodes
        # TODO: maybe allow connections across many layers?
        assert to_node.component in self.sub_components.values()
        assert not to_node.name.startswith('_')

        self.nodes[from_name].connected_to.append(to_node)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} @ {self.get_path()}>'


class AtomicComponent(Component):
    def add_component(self, component: 'Component') -> 'Component':
        raise Exception('cannot add sub component to atomic component')

    @abc.abstractmethod
    def ngspice_line(self, comp_id: str, nodes: typ.Dict[str, str]) -> str:
        pass
