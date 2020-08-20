import pandas as pd
from tqdm import tqdm

no_space_join_1 = ['!', '%', ',', '-', '.', '/', ':', ';', '?', '_', '`', '|', '‐', '‒', '–', '—',]
no_space_join_2 = ['" ', "' "]

def join_fragments(fragment_list):
    result = ""
    for fragment in fragment_list:
        if fragment[0] in no_space_join_1 or fragment[0:2] in no_space_join_2:
            result += fragment
        else:
            result += " " + fragment
    return result[1:]

def main():
    df = pd.read_csv("C:\\Users\\Banjamin\\sentence-pair-extraction\\sentences_for_tokenizer_correction.tsv", sep="\t")
    df = df.astype(str)

    half_sentence_indexes = list(df[~df.original.apply(lambda x: x[0].isupper()) & ~df.revised.apply(lambda x: x[0].isupper())].index)

    # Approx 16 min
    combine_index_lists = [[-1]]
    max_index = 0
    for i in tqdm(half_sentence_indexes, ascii=True):
        if i > max_index:
            index_list = [i-1]
            while i in half_sentence_indexes:
                index_list.append(i)
                i += 1
            combine_index_lists.append(index_list)
            max_index = max(max_index, max(index_list))
    combine_index_lists.pop(0)

    # Approx 8 hours
    for index_list in tqdm(combine_index_lists, ascii=True):
        start, stop = index_list[0], index_list[-1]
        if start >= 0:
            temp_df = df.loc[start:stop]
            original = temp_df.groupby(temp_df["file"])["original"].transform(lambda x: join_fragments(x)).loc[start]
            revised = temp_df.groupby(temp_df["file"])["revised"].transform(lambda x: join_fragments(x)).loc[start]

            df.loc[start].original = original
            df.loc[start].revised = revised

            df = df.drop(index_list[1:])
    
    df.to_csv("C:\\Users\\Banjamin\\sentence-pair-extraction\\sentences_for_tokenizer_correction.tsv", sep="\t", index=False)

if __name__ == "__main__":
    main()