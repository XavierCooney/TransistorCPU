import typing as typ
from collections import defaultdict, deque

import component as comp


class NetList:
    def __init__(self) -> None:
        self.atomic_componenets: typ.List[comp.AtomicComponent] = []
        self.nodes: typ.List[comp.Node] = []
        self.connections: typ.List[typ.Tuple[comp.Node, comp.Node]] = []
        ConnectedToType = typ.Dict[comp.Node, typ.List[comp.Node]]
        self.connected_to: ConnectedToType = defaultdict(list)
        self.coalesced_nodes: typ.List[typ.List[comp.Node]] = []
        self.coalesced_numbering: typ.Dict[comp.Node, int] = {}

    def resolve_component(self, component: 'comp.Component') -> None:
        for node in component.nodes.values():
            self.nodes.append(node)

        if isinstance(component, comp.AtomicComponent):
            self.atomic_componenets.append(component)
        else:
            if not len(component.sub_components) >= 1:
                raise ValueError(
                    f'{component.component_name} needs subcomponents'
                )
            for sub_component in component.sub_components.values():
                self.resolve_component(sub_component)

        for node in component.nodes.values():
            for other_node in node.connected_to:
                assert other_node in self.nodes
                self.connections.append((node, other_node))
                self.connected_to[node].append(other_node)
                self.connected_to[other_node].append(node)

    def dump_info(self) -> str:
        string_segments = []

        string_segments.append(' == Nodes == \n')
        for node_num, node in enumerate(self.nodes):
            string_segments.append(f'   {node_num:3}: {node.get_path()}\n')

        string_segments.append('\n == Coalesced == \n')
        for group_num, group in enumerate(self.coalesced_nodes):
            if group:
                string_segments.append(
                    f'  {group_num:3} - {group[0].get_path()}\n'
                )
                for node in group[1:]:
                    string_segments.append(f'        {node.get_path()}\n')
            else:
                string_segments.append(f'  {group_num:3} - [empty]\n')

        return ''.join(string_segments)

    def coalesce_nodes(self) -> None:
        seen_nodes: typ.Set[comp.Node] = set()

        # self.coalesced_nodes.append([])  # Ground reference

        for starting_node in self.nodes:
            if starting_node in seen_nodes:
                continue

            next_node_group: typ.List[comp.Node] = []
            seen_nodes.add(starting_node)

            nodes_to_check = deque([starting_node])
            while nodes_to_check:
                top_node = nodes_to_check.popleft()
                next_node_group.append(top_node)

                for neighbour in self.connected_to[top_node]:
                    if neighbour in seen_nodes:
                        continue
                    nodes_to_check.append(neighbour)
                    seen_nodes.add(neighbour)

            self.coalesced_nodes.append(next_node_group)

        for group_num, group in enumerate(self.coalesced_nodes):
            for node in group:
                self.coalesced_numbering[node] = group_num

    @classmethod
    def make(cls, root: 'comp.Component') -> 'NetList':
        netlist = cls()
        netlist.resolve_component(root)

        # ensure each node is actually doing something
        for node in netlist.nodes:
            if len(netlist.connected_to[node]) < 1:
                raise ValueError(f'Unconnected node: {node.get_path()}')

        netlist.coalesce_nodes()

        return netlist
