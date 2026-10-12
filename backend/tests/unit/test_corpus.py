from app.retrieval.corpus import Topic, chunk_topic, parse_medlineplus, read_chunks, summary_blocks, write_chunks

SUMMARY = """
<p>You can have a sore throat for many reasons. Other causes can include:</p>
<ul><li>Allergies</li><li>Smoking</li></ul>
<p>What is strep throat?</p>
<p>It is an infection caused by bacteria.</p>
<p class="">NIH: National Institute of Allergy and Infectious Diseases</p>
"""


def test_lists_and_headings_stay_with_what_they_introduce():
    blocks, credit = summary_blocks(SUMMARY)
    assert blocks == [
        "You can have a sore throat for many reasons. Other causes can include:\n- Allergies\n- Smoking",
        "What is strep throat?\nIt is an infection caused by bacteria.",
    ]
    assert credit == "NIH: National Institute of Allergy and Infectious Diseases"


def test_nested_lists_are_indented_not_repeated():
    blocks, _ = summary_blocks("<p>Treatments include:</p><ul><li>Surgery to<ul><li>Remove clots</li></ul></li>"
                               "<li>Medicines</li></ul>")
    assert blocks == ["Treatments include:\n- Surgery to\n  - Remove clots\n- Medicines"]


def test_a_single_short_block_is_content_not_a_credit():
    assert summary_blocks("<p>Hodgkin lymphoma can usually be cured if it is found early</p>")[1] == ""


def topic(blocks, synonyms=("Pharyngitis",)):
    return Topic(id="1", title="Sore Throat", url="https://medlineplus.gov/sorethroat.html",
                 synonyms=list(synonyms), groups=[], organization="NIH", blocks=blocks)


def test_chunks_stay_under_the_target_and_split_between_blocks():
    chunks = chunk_topic(topic(["a" * 300, "b" * 300, "c" * 300]), target_chars=700, max_synonyms=10)
    assert [c.text for c in chunks] == ["a" * 300 + "\n" + "b" * 300, "c" * 300]


def test_long_lists_are_split_between_items():
    long_list = "Symptoms include:\n" + "\n".join(f"- symptom number {i} " + "x" * 40 for i in range(20))
    chunks = chunk_topic(topic([long_list]), target_chars=300, max_synonyms=10)
    assert all(len(c.text) <= 300 for c in chunks)
    assert all(line.startswith("- ") or line == "Symptoms include:" for c in chunks for line in c.text.split("\n"))


def test_every_chunk_carries_the_topic_header():
    chunks = chunk_topic(topic(["a" * 300, "b" * 300]), target_chars=300, max_synonyms=10)
    assert len(chunks) == 2
    assert all(c.embedding_text.startswith("Sore Throat (also called: Pharyngitis)\n") for c in chunks)
    assert [c.id for c in chunks] == ["1-0", "1-1"] and chunks[1].organization == "NIH"


def test_synonym_count_is_capped():
    chunk = chunk_topic(topic(["text"], synonyms=[f"name{i}" for i in range(20)]), 800, max_synonyms=3)[0]
    assert chunk.header == "Sore Throat (also called: name0, name1, name2)"


def test_parse_keeps_english_topics_and_dedupes_synonyms(tmp_path):
    xml = tmp_path / "topics.xml"
    xml.write_text("""<?xml version="1.0" encoding="UTF-8"?><health-topics>
      <health-topic title="Sore Throat" url="https://medlineplus.gov/sorethroat.html" id="1" language="English">
        <also-called>Pharyngitis</also-called><see-reference>Pharyngitis</see-reference>
        <see-reference>Sore Throat</see-reference><group>Ear, Nose and Throat</group>
        <full-summary>&lt;p&gt;It hurts to swallow.&lt;/p&gt;</full-summary>
      </health-topic>
      <health-topic title="Dolor de garganta" url="https://medlineplus.gov/spanish/x.html" id="2" language="Spanish">
        <full-summary>&lt;p&gt;Duele.&lt;/p&gt;</full-summary>
      </health-topic></health-topics>""", encoding="utf-8")
    topics = parse_medlineplus(xml)
    assert [t.title for t in topics] == ["Sore Throat"]
    assert topics[0].synonyms == ["Pharyngitis"]  # duplicates and the title itself removed
    assert topics[0].groups == ["Ear, Nose and Throat"]


def test_chunks_round_trip_through_jsonl(tmp_path):
    chunks = chunk_topic(topic(["a" * 300, "b" * 300]), target_chars=300, max_synonyms=10)
    path = tmp_path / "chunks.jsonl"
    assert write_chunks(chunks, path) == 2
    assert list(read_chunks(path)) == chunks
