"""Utils for tacking graph homophily and heterophily"""
# pylint: disable=W0611
from . import function as fn

try:
    import torch
except ImportError:
    HAS_TORCH = False
else:
    HAS_TORCH = True

__all__ = ["node_homophily", "edge_homophily", "linkx_homophily"]


def check_pytorch():
    """Check if PyTorch is the backend."""
    if HAS_TORCH is False:
        raise ModuleNotFoundError(
            "This function requires PyTorch to be the backend."
        )


def get_long_edges(graph):
    """Internal function for getting the edges of a graph as long tensors."""
    src, dst = graph.edges()
    return src.long(), dst.long()


def node_homophily(graph, y):
    r"""Homophily measure from `Geom-GCN: Geometric Graph Convolutional
    Networks <https://arxiv.org/abs/2002.05287>`__

    We follow the practice of a later paper `Large Scale Learning on
    Non-Homophilous Graphs: New Benchmarks and Strong Simple Methods
    <https://arxiv.org/abs/2110.14446>`__ to call it node homophily.

    Mathematically it is defined as follows:

    .. math::
      \frac{1}{|\mathcal{V}|} \sum_{v \in \mathcal{V}} \frac{ | \{u
      \in \mathcal{N}(v): y_v = y_u \} |  } { |\mathcal{N}(v)| },

    where :math:`\mathcal{V}` is the set of nodes, :math:`\mathcal{N}(v)` is
    the predecessors of node :math:`v`, and :math:`y_v` is the class of node
    :math:`v`.

    Parameters
    ----------
    graph : DGLGraph
        The graph.
    y : torch.Tensor
        The node labels, which is a tensor of shape (|V|).

    Returns
    -------
    float
        The node homophily value.

    Examples
    --------
    >>> import dgl
    >>> import torch

    >>> graph = dgl.graph(([1, 2, 0, 4], [0, 1, 2, 3]))
    >>> y = torch.tensor([0, 0, 0, 0, 1])
    >>> dgl.node_homophily(graph, y)
    0.6000000238418579
    """
    check_pytorch()
    with graph.local_scope():
        # Handle the case where graph is of dtype int32.
        src, dst = get_long_edges(graph)
        # Compute y_v = y_u for all edges.
        graph.edata["same_class"] = (y[src] == y[dst]).float()
        graph.update_all(
            fn.copy_e("same_class", "m"), fn.mean("m", "same_class_deg")
        )
        return graph.ndata["same_class_deg"].mean(dim=0).item()


def edge_homophily(graph, y):
    r"""Homophily measure from `Beyond Homophily in Graph Neural Networks:
    Current Limitations and Effective Designs
    <https://arxiv.org/abs/2006.11468>`__

    Mathematically it is defined as follows:

    .. math::
      \frac{| \{ (u,v) : (u,v) \in \mathcal{E} \wedge y_u = y_v \} | }
      {|\mathcal{E}|},

    where :math:`\mathcal{E}` is the set of edges, and :math:`y_u` is the class
    of node :math:`u`.

    Parameters
    ----------
    graph : DGLGraph
        The graph.
    y : torch.Tensor
        The node labels, which is a tensor of shape (|V|).

    Returns
    -------
    float
        The edge homophily ratio value.

    Examples
    --------
    >>> import dgl
    >>> import torch

    >>> graph = dgl.graph(([1, 2, 0, 4], [0, 1, 2, 3]))
    >>> y = torch.tensor([0, 0, 0, 0, 1])
    >>> dgl.edge_homophily(graph, y)
    0.75
    """
    check_pytorch()
    with graph.local_scope():
        # Handle the case where graph is of dtype int32.
        src, dst = get_long_edges(graph)
        # Compute y_v = y_u for all edges.
        edge_indicator = (y[src] == y[dst]).float()
        return edge_indicator.mean(dim=0).item()


def linkx_homophily(graph, y):
    r"""Homophily measure from `Large Scale Learning on Non-Homophilous Graphs:
    New Benchmarks and Strong Simple Methods
    <https://arxiv.org/abs/2110.14446>`__

    Mathematically it is defined as follows:

    .. math::
      \frac{1}{C-1} \sum_{k=1}^{C} \max \left(0, \frac{\sum_{v\in C_k}|\{u\in
      \mathcal{N}(v): y_v = y_u \}|}{\sum_{v\in C_k}|\mathcal{N}(v)|} -
      \frac{|\mathcal{C}_k|}{|\mathcal{V}|} \right),

    where :math:`C` is the number of node classes, :math:`C_k` is the set of
    nodes that belong to class k, :math:`\mathcal{N}(v)` are the predecessors
    of node :math:`v`, :math:`y_v` is the class of node :math:`v`, and
    :math:`\mathcal{V}` is the set of nodes.

    Parameters
    ----------
    graph : DGLGraph
        The graph.
    y : torch.Tensor
        The node labels, which is a tensor of shape (|V|).

    Returns
    -------
    float
        The homophily value.

    Examples
    --------
    >>> import dgl
    >>> import torch

    >>> graph = dgl.graph(([0, 1, 2, 3], [1, 2, 0, 4]))
    >>> y = torch.tensor([0, 0, 0, 0, 1])
    >>> dgl.linkx_homophily(graph, y)
    0.19999998807907104
    """
    check_pytorch()
    with graph.local_scope():
        # Compute |{u\in N(v): y_v = y_u}| for each node v.
        # Handle the case where graph is of dtype int32.
        src, dst = get_long_edges(graph)
        # Compute y_v = y_u for all edges.
        graph.edata["same_class"] = (y[src] == y[dst]).float()
        graph.update_all(
            fn.copy_e("same_class", "m"), fn.sum("m", "same_class_deg")
        )

        deg = graph.in_degrees().float()
        num_nodes = graph.num_nodes()
        num_classes = y.max(dim=0).values.item() + 1

        value = 0
        for k in range(num_classes):
            # Get the nodes that belong to class k.
            class_mask = y == k
            same_class_deg_k = graph.ndata["same_class_deg"][class_mask].sum()
            deg_k = deg[class_mask].sum()
            num_nodes_k = class_mask.sum()
            value += max(0, same_class_deg_k / deg_k - num_nodes_k / num_nodes)

        return value.item() / (num_classes - 1)
