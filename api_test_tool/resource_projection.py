"""Independent resource previews, without unrelated archived result bodies."""
import copy


def copy_node(node):
    # Matching never reads case_history. Keep the original node/history intact
    # for reports, continuation and audit; never persist this whole projection.
    # All scheduling fields remain deeply isolated, including nested protection,
    # checkpoints and handoffs. Only the explicit resource fields are applied.
    return copy.deepcopy({key: value for key, value in node.items() if key != 'case_history'})
