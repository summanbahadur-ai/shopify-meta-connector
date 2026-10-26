import pytest
from app.messaging.policy_formatter import policy_html_to_text


def test_paragraphs_lists_entities_and_links():
    html = '<h2>Returns</h2><p>Keep your receipt &amp; packaging.</p><ol><li>Contact us.</li><li>Send the item.</li></ol><p>See <a href="https://example.com/returns">return instructions</a>.</p>'
    text = policy_html_to_text(html)
    assert 'Returns\n\nKeep your receipt & packaging.' in text
    assert '1. Contact us.\n2. Send the item.' in text
    assert 'return instructions (https://example.com/returns)' in text
    assert '<' not in text


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty(value):
    assert policy_html_to_text(value) == ''


def test_hidden_content_and_unsafe_links():
    text = policy_html_to_text('<p>Return <strong>within 7 days</strong>.</p><script>bad()</script><style>hidden</style><!-- comment --><ul><li>Unused</li></ul><a href="javascript:bad()">Help</a>')
    assert 'Return within 7 days.' in text and '- Unused' in text
    assert 'bad()' not in text and 'hidden' not in text and 'comment' not in text
    assert 'Help' in text and 'javascript' not in text


def test_text_line_breaks_and_no_truncation():
    assert policy_html_to_text('First\nSecond') == 'First\nSecond'
    assert policy_html_to_text('<p>First<br>Second</p>') == 'First\nSecond'
    assert len(policy_html_to_text('<p>' + 'x' * 5000 + '</p>')) == 5000
