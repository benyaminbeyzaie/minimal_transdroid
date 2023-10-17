import networkx as nx
from os.path import join, exists
import json
import matplotlib.pyplot as plt
import os


class NavGraph:
    EDGE_TYPES = ["GUI", "OPTION_MENU"]
    LOCATOR_TYPES = ["ID", "TEXT", "CONTENT-DESC"]
    ACTIONS = ["CLICK"]

    def __init__(self, model_path):
        self.G = nx.MultiDiGraph()
        self.graphName = model_path.rpartition("/")[-1]
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

    def paths_between_nodes(self, n_from, n_to):
        if n_from not in self.G or n_to not in self.G:
            return []
        paths_map = {}  # hash map to avoid duplicate path
        if n_from == n_to:
            if self.G.get_edge_data(n_from, n_to):
                events = set(self.G.get_edge_data(n_from, n_to).keys())
                for e in events:
                    path = [(n_from, e), (n_to, None)]
                    paths_map[NavGraph.path_signature(path)] = path
            paths = list(paths_map.values())
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
                paths_map[NavGraph.path_signature(path)] = path
                # if n_to has self-loops, repeat them
                if self.G.get_edge_data(n_to, n_to):
                    events = set(self.G.get_edge_data(n_to, n_to).keys())
                    for e in events:
                        path_end_repeated = path[:]
                        path_end_repeated.pop()
                        path_end_repeated.append((n_to, e))
                        paths_map[
                            NavGraph.path_signature(path_end_repeated)
                        ] = path_end_repeated
            paths = list(paths_map.values())
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

    @staticmethod
    def normalize_activity_name(input_string):
        parts = input_string.split(".")

        if len(parts) >= 3:
            result = ".".join(parts[-3:])
            return result
        else:
            return input_string

    def visualize_navgraph(self, save_path):
        # Create a visualization of the navigation graph
        pos = nx.spring_layout(self.G, seed=42)
        plt.figure(figsize=(12, 8))
        edge_labels = {}
        for u, v, _ in self.G.edges(data=True):
            # u = self.normalize_activity_name(u)
            # v = self.normalize_activity_name(v)
            edge_labels[(u, v)] = ""

        nx.draw(
            self.G,
            pos,
            with_labels=True,
            node_size=500,
            node_color="lightblue",
            font_size=8,
        )
        nx.draw_networkx_edge_labels(
            self.G, pos, edge_labels=edge_labels, font_size=8, font_color="red"
        )
        plt.title("Navigation Graph Visualization")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path)
        plt.show()


if __name__ == "__main__":
    navGraph = NavGraph("../NavGraph/app/model/com.owncloud.android_215")
    print(len(navGraph.G.nodes))
    print(len(navGraph.G.edges))
    navGraph.visualize_navgraph(f"navgraph_visuals/{navGraph.graphName}.png")
