"""Generates embeddings for the caption, slide, and frame databases."""

import json
from pathlib import Path

import pandas as pd

from src.config import EMBEDDING_MODEL,EMBEDDING_DIMENSIONS
from src.embedding_client import embed_texts
from src.database_io import EMBEDDING_DIR, load_database
from src.checkpoints import append_jsonl_checkpoint, load_jsonl_checkpoint

EMBEDDING_BATCH_SIZE = 32


def embedding_text(database_df:pd.DataFrame,
                   database_name:str,) -> pd.DataFrame:

    database_df = database_df.copy()

    if database_name == 'caption_database':

        database_df['embedding_text'] =(
            database_df['text'].fillna("").astype(str)
        )

    else:
        database_df['embedding_text'] = (
            database_df['searchable_text'].fillna("").astype(str))

    database_df = database_df[database_df['embedding_text'].str.strip() !=""].copy()

    return database_df.reset_index(drop=True)

def generate_embeddings(texts:list[str],) ->list[list[float]]:
    return embed_texts(texts, batch_size=EMBEDDING_BATCH_SIZE).tolist()

def generate_database_embeddings(database_name:str,)->Path:

    EMBEDDING_DIR.mkdir(parents=True,exist_ok=True)

    database_df = load_database(database_name)

    database_df = embedding_text(database_df,database_name)

    checkpoint_path = EMBEDDING_DIR / f"{database_name}_embedding_checkpoints.jsonl"

    output_path = EMBEDDING_DIR / f"{database_name}_embeddings.json"

    embedding_records = load_jsonl_checkpoint(checkpoint_path)

    completed_ids ={record['record_id'] for record in embedding_records}


    pending_df = database_df[~ database_df['record_id'].isin(completed_ids)].copy()


    print('\n',database_name,'database:')
    print('records expected:',len(database_df))
    print('previously completed:',len(completed_ids))
    print('pending records:',len(pending_df))


    for batch_start in range(0,len(pending_df),EMBEDDING_BATCH_SIZE):

        batch_df= pending_df.iloc[batch_start:batch_start+EMBEDDING_BATCH_SIZE]

        texts = batch_df['embedding_text'].tolist()

        embeddings = generate_embeddings(texts)

        if len(embeddings)!=len(batch_df):
            raise ValueError(f"embeddings batch size mismatch: {len(embeddings)} != {len(batch_df)}")

        for (_,row), embedding in zip(batch_df.iterrows(),embeddings):

            embedding_record = {
                'record_id':row['record_id'],
                'lecture_id':row['lecture_id'],
                'content_type':row['content_type'],
                'embedding_model':EMBEDDING_MODEL,
                'embedding_dimensions':EMBEDDING_DIMENSIONS,
                'embedding':embedding,}

            append_jsonl_checkpoint(checkpoint_path,embedding_record)

            embedding_records.append(embedding_record)

            print(f"embedded: {len(embedding_records)}/{len(database_df)}")


    with open(output_path, "w", encoding='utf-8') as file:

        json.dump(embedding_records,file,ensure_ascii=False)

    print('saved embedding checkpoints to',output_path)
    return output_path

def generate_all_database_embeddings()->None:
    database_names = [
        'caption_database',
        'slide_database',
        'frame_database',
    ]

    for database_name in database_names:
        generate_database_embeddings(database_name)

    print('all database embeddings completed')


if __name__ == "__main__":
    generate_all_database_embeddings()




