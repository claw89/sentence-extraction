import pandas as pd
from dask import dataframe as dd
from dask.diagnostics import ProgressBar
import editdistance
import numpy as np

ProgressBar().register()

def get_extent_of_changes(row):
    max_length = max(len(row.original), len(row.revised))
    if max_length < 895:
        return editdistance.eval(row.original, row.revised) / max_length
    else:
        return np.nan

def main():
    dfd = dd.read_csv("C:\\Users\\Banjamin\\sentence-pair-extraction\\sentences.tsv", 
                      sep="\t", 
                      names=["file", "original", "revised"],
                      dtype={"file": 'object', 
                             "original": 'object', 
                             "revised": 'object'},
                      blocksize=64000000)
    dfd = dfd.fillna(" ")
    changes = dfd.apply(lambda row: get_extent_of_changes(row), axis=1)
    
    store = pd.HDFStore("editdistance_store.h5")
    
    store.put('changes',
              changes.compute(),
              format="table",
              data_columns=True)

if __name__ == "__main__":
    main()