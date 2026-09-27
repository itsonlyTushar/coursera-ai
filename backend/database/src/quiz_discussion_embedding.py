"""Generates embeddings for the quiz and discussion databases."""
import json
import pandas as pd
from typing import Any
from src.embedding_client import embed_texts
from src.database_io import EMBEDDING_DIR, load_database
from src.qdrant_common import (
    MODEL_NAME,
    VECTOR_DIMENSIONS as EMBEDDING_DIMENSIONS,
    parse_serialized_value,
)

BATCH_SIZE = 35

EXPECTED_COUNT = {
    "quiz_database":456,
    "discussion_database":570,
}

def format_for_embedding(value: Any) -> str:

    value = parse_serialized_value(value)

    if value is None:
        return ""

    if isinstance(value, dict):
        return "; ".join(
            f"{key}:{format_for_embedding(item)}"
            for key, item in value.items())

    if isinstance(value, list):
        return ", ".join(format_for_embedding(item) for item in value)

    return str(value).strip()

def build_quiz_text(row:pd.Series)->str:

    feilds=[
        ("Question", row.get("question")),
        ("Options", row.get("options")),
        ("Correct answer", row.get("correct_answer")),
        ("Explanation", row.get("explanation")),
        ("Topic", row.get("topic")),
        ("Difficulty", row.get("difficulty_signals")),
        ("Concept tags", row.get("concept_tags")),
        ("Question type", row.get("question_type")),
    ]

    return "\n".join(f"{label}:{formatted}"
                     for label,value in feilds
                     if (formatted:= format_for_embedding(value)))

def build_discussion_text(row:pd.Series)->str:

    feilds=[
        ("Thread title", row.get("thread_title")),
        ("Post", row.get("post_text")),
        ("Topic", row.get("topic")),
        ("Recurring theme", row.get("recurring_theme")),
        ("Concept tags", row.get("concept_tags")),
        ("Sentiment", row.get("sentiment")),
        ("Friction type", row.get("friction_type")),
        ("Severity", row.get("severity")),
    ]

    return "\n".join(f"{label}:{formatted}"
                     for label,value in feilds
                     if (formatted:= format_for_embedding(value)))

def generate_embeddings(database_name:str,
                        content_type:str)->None:

    database_df = load_database(
        database_name,
        required_columns={"record_id", "lecture_id"},
        expected_count=EXPECTED_COUNT[database_name],
        require_lecture_id=True,
    )

    if content_type=="quiz":

        searchable_texts = [
            build_quiz_text(row)
            for _, row in database_df.iterrows()
        ]
    elif content_type=="discussion":

        searchable_texts = [
            build_discussion_text(row)
            for _, row in database_df.iterrows()
        ]
    else:
        raise ValueError(f"Invalid content type: {content_type}")


    empty_text_ids =[
        database_df.iloc[index]["record_id"]
        for index,text in enumerate(searchable_texts)
        if not text.strip()
    ]

    if empty_text_ids:
        raise ValueError(f"{database_name} database has empty text ids: {empty_text_ids[:10]}")

    print(f"\n Generating {len(searchable_texts)} embeddings for {content_type}")

    vectors= embed_texts(searchable_texts, batch_size=BATCH_SIZE)

    if vectors.shape != (len(database_df),EMBEDDING_DIMENSIONS):
        raise ValueError(f"uneexpected embedding shape for {database_name} database: {vectors.shape}")

    embedding_records=[]

    for row_index,row in database_df.iterrows():
        embedding_records.append({
            'record_id':str(row['record_id']),
            'lecture_id':str(row['lecture_id']),
            'content_type':content_type,
            'embedding_model':MODEL_NAME,
            'embedding_dimensions':EMBEDDING_DIMENSIONS,
            'embedding':vectors[row_index].astype(float).tolist(),
        })

    output_path = (EMBEDDING_DIR / f"{database_name}_embeddings.json")

    temporary_path = output_path.with_suffix(".json.tmp")

    if output_path.exists():
        raise FileExistsError(f"Output file already exists: {output_path}")

    EMBEDDING_DIR.mkdir(parents=True, exist_ok=True)

    with open(temporary_path,'w',encoding='utf-8') as file:
        json.dump(embedding_records,file,ensure_ascii=False)

    temporary_path.replace(output_path)
    print(f"Saved {len(embedding_records)} embeddings to {output_path}")

def main()->None:
    print('embedding via HF Inference API: ', MODEL_NAME)

    generate_embeddings(database_name="quiz_database",
                        content_type="quiz")

    generate_embeddings(database_name="discussion_database",
                        content_type="discussion")

    print("\n quiz and discussion embeddings generated")


if __name__ == "__main__":
    main()
    
    