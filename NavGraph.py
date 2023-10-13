import networkx as nx
from os.path import join, exists
import json

# local imports
from logger import logger


class NavGraph:
    EDGE_TYPES = ["GUI", "OPTION_MENU"]
    LOCATOR_TYPES = ["ID", "TEXT", "CONTENT-DESC"]
    ACTIONS = ["CLICK"]

    def __init__(self, model_path):
        self.G = nx.MultiDiGraph()
        if not exists(join(model_path, "graph.txt")):
            return
        with open(join(model_path, "rIdToName.json"), "r") as f:
            rid_name = json.load(f)
        rid_name[
            "16908332"
        ] = "android.R.id.home"  # the home/back icon in the action bar
        with open(join(model_path, "graph.txt"), "r") as f:
            nodes = set()
            for line in f:
                if line.startswith("Nodes:") or line.startswith("Edges:"):
                    mode = "node" if line.startswith("Nodes:") else "edge"
                    continue
                if mode == "node":
                    # e.g., org.wordpress.android.ui.prefs.MyProfileActivity (Activity)
                    n, n_type = line.split()[0], line.split()[1]
                    n_type = n_type.replace("(", "").replace(")", "")
                    if n_type == "Activity":
                        nodes.add(n)
                else:  # "edge" mode
                    # e.g., org.wordpress.android.ui.plugins.PluginDetailActivity -> org.wordpress.android.ui.plugins.PluginDetailActivity (GUI:ID 2131297292)
                    n_from = line.split("->")[0].strip()
                    n_to = line.split("->")[1].split()[0].strip()
                    if n_from in nodes and n_to in nodes:
                        edge = line.split("(")[1].replace(")", "")
                        e_type, e_id = edge.split(":")[0], edge.split(":")[1]
                        if e_type in NavGraph.EDGE_TYPES and e_id.startswith("ID"):
                            r_id = e_id.split()[1]
                            if r_id != "null":
                                self.G.add_edge(
                                    n_from,
                                    n_to,
                                    ":".join([e_type, "ID", rid_name[r_id], "CLICK"]),
                                )

    def add_edge(self, n_from, n_to, label):
        prev_edges = len(self.G.edges)
        self.G.add_edge(n_from, n_to, label)
        current_edges = len(self.G.edges)
        if current_edges > prev_edges:
            logger.info(f"New edge added: {n_from} -> {n_to} ({label})")

    def paths_between_nodes(self, n_from, n_to):
        if n_from not in self.G or n_to not in self.G:
            return []
        pmap = {}  # hash map to avoid duplicate path
        if n_from == n_to:
            if self.G.get_edge_data(n_from, n_to):
                events = set(self.G.get_edge_data(n_from, n_to).keys())
                for e in events:
                    path = [(n_from, e), (n_to, None)]
                    pmap[NavGraph.path_signature(path)] = path
            paths = list(pmap.values())
            paths.insert(0, [(n_from, None), (n_to, None)])
            return paths
        else:
            for node_list in nx.all_simple_paths(self.G, source=n_from, target=n_to):
                path = []
                for i in range(len(node_list) - 1):
                    u, v = node_list[i], node_list[i + 1]
                    events = set(self.G.get_edge_data(u, v).keys())
                    e = NavGraph.top_event(
                        events
                    )  # only consider/prioritize one event between u and v for now
                    path.append((u, e))
                path.append((n_to, None))
                pmap[NavGraph.path_signature(path)] = path
                # if n_to has self-loops, repeat them
                if self.G.get_edge_data(n_to, n_to):
                    events = set(self.G.get_edge_data(n_to, n_to).keys())
                    for e in events:
                        path_end_repeated = path[:]
                        path_end_repeated.pop()
                        path_end_repeated.append((n_to, e))
                        pmap[
                            NavGraph.path_signature(path_end_repeated)
                        ] = path_end_repeated
            paths = list(pmap.values())
            paths.sort(key=lambda x: len(x))  # prefer shorter paths
            return paths

    @staticmethod
    def path_signature(path):
        # e.g., [("node1", "action1"), ("node2", "action2"), ("node3", None)]
        return "!".join(node + "+" + str(action) for node, action in path)

    @staticmethod
    def top_event(events):
        g, t, c, o = [], [], [], []
        for e in events:
            if "GUI:ID" in e:
                g.append(e)
            elif "GUI:TEXT" in e:
                t.append(e)
            elif "GUI:CONTENT-DESC" in e:
                c.append(e)
            elif "OPTION_MENU:ID" in e:
                o.append(e)
            else:
                assert False, "Unknown event type"
        g.sort()
        t.sort()
        c.sort()
        o.sort()
        res = g + t + c + o
        return res[0]


if __name__ == "__main__":
    # G = nx.MultiDiGraph()
    # G.add_node("a1")
    # G.add_node("a2")
    # G.add_edge("a1", "a2", "1")
    # G.add_edge("a1", "a2", "2")
    # G.add_edge("a1", "a1", "3")
    # G.add_edge("a1", "a1", "4")
    # G.add_node("a1")
    # G.add_edge("a8", "a8", "5")
    # print([p for p in nx.all_simple_paths(G, "a1", "a2")])
    # print(G.number_of_edges("a1", "a9"))
    # print(G.nodes)
    # print(G.edges)
    # print(G.number_of_edges('a1', 'a2'))
    # print(G.get_edge_data('a1', 'a2'))

    navGraph = NavGraph("../../NavGraph/app/model/wpandroid-14.3-universal")
    print(len(navGraph.G.nodes))
    print(len(navGraph.G.edges))
    navGraph.add_edge(
        "org.wordpress.android.ui.accounts.HelpActivity",
        "org.wordpress.android.ui.accounts.HelpActivity",
        "label",
    )
    print(
        navGraph.paths_between_nodes(
            "org.wordpress.android.ui.plugins.PluginDetailActivity",
            "org.wordpress.android.ui.plugins.PluginDetailActivity",
        )
    )
    print(
        navGraph.paths_between_nodes(
            "org.wordpress.android.ui.AppLogViewerActivity",
            "org.wordpress.android.ui.accounts.HelpActivity",
        )
    )
