import pytest

from mqtt_broker.gui.trees import TopicTree

TOPICS = [
    "plant/line1/temperature",
    "plant/line1/pressure",
    "plant/line2/status",
    "plant",
    "alarms/line1/overtemp",
]


@pytest.fixture
def tree(qtbot):
    widget = TopicTree()
    qtbot.addWidget(widget)
    for topic in TOPICS:
        widget.update_topic(topic, 1)
    return widget


def node(tree: TopicTree, path: str):
    return tree._nodes[path]


def test_no_filter_shows_everything(tree):
    assert tree.visible_topics() == sorted(TOPICS)
    assert not any(n.isHidden() for n in tree._nodes.values())


def test_substring_filter_keeps_ancestors_of_matches(tree):
    tree.set_filter("pressure")
    # "plant" is also a topic; it stays visible as the ancestor of a match
    assert tree.visible_topics() == ["plant", "plant/line1/pressure"]
    assert not node(tree, "plant").isHidden()
    assert not node(tree, "plant/line1").isHidden()
    assert node(tree, "plant/line2").isHidden()
    assert node(tree, "alarms").isHidden()


def test_intermediate_topic_matches_without_children(tree):
    tree.set_filter("plant")
    assert "plant" in tree.visible_topics()
    tree.set_filter("plant/+")
    assert tree.visible_topics() == []
    tree.set_filter("plant/#")
    assert tree.visible_topics() == sorted(t for t in TOPICS if t.startswith("plant"))


def test_filter_is_trimmed_and_case_insensitive(tree):
    tree.set_filter("  LINE2  ")
    assert tree.visible_topics() == ["plant", "plant/line2/status"]


def test_topics_added_while_filtered_respect_the_filter(tree):
    tree.set_filter("+/+/status")
    tree.update_topic("plant/line3/status", 1)
    tree.update_topic("other/area/temp", 1)
    tree.update_topic("plant/line1/temperature", 2)
    assert tree.visible_topics() == ["plant", "plant/line2/status", "plant/line3/status"]
    assert node(tree, "plant/line1").isHidden()
    assert node(tree, "other").isHidden()


def test_clearing_filter_restores_all_and_clear_topics_resets(tree):
    tree.set_filter("nothing-matches")
    assert tree.visible_topics() == []
    tree.set_filter("")
    assert tree.visible_topics() == sorted(TOPICS)
    tree.clear_topics()
    assert tree.topics() == []
    tree.update_topic("fresh/topic", 1)
    assert tree.visible_topics() == ["fresh/topic"]
