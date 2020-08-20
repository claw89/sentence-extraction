import os
import csv
import pickle
import json
import argparse
import time
import pythoncom
from win32com.client import Dispatch
from tqdm.auto import tqdm
import spacy
import logging
import random
import re

nlp = spacy.load("en_core_web_sm")
myWord = Dispatch("Word.Application")
    
my_parser = argparse.ArgumentParser()
my_parser.add_argument('Path',
                       metavar='path',
                       type=str,
                       help='the path containing edited documents')
my_parser.add_argument('Tokenizer',
                       metavar='tokenizer',
                       type=str,
                       help='string indicating the sentence tokenizer: "nltk" or "spacy"')

my_parser.add_argument('--window', 
                       nargs='?', 
                       default=10, 
                       type=int,
                       help='window size for CheckJumps macro; sentences may not be extracted if the window size is too small.')
my_parser.add_argument('-r',
                       '--reset',
                       action='store_true',
                       help='reset sentences.tsv')
my_parser.add_argument('-v',
                       '--verbose',
                       action='store_true',
                       help='show detailed information')
my_parser.add_argument('-c',
                       '--correct',
                       action='store_true',
                       help='correct cases with the wrong number of sentences extracted in previous executions')
args = my_parser.parse_args()
docs_path = args.Path
tokenizer = args.Tokenizer
if tokenizer == "nltk":
    with open("sentence_tokenizer", "rb") as file:
        sentence_tokenizer = pickle.load(file)
if args.reset:
    file_mode = "w"
else:
    file_mode = "at"

# create logger
logger = logging.getLogger('build_sentence_dataset_logger')
logger.setLevel(logging.DEBUG)
ch = logging.FileHandler("buildSentenceDataset.log", file_mode, encoding="utf-8")
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(levelname)s:root:%(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

def reverse_index_conversion(x, jump_points):
    addition = 0
    for index in jump_points:
        if x >= index - addition:
            addition += 1
        else:
            return x + addition
    return x + addition

def get_sentence_pairs(path):
    """
    Extract lists of the original and revised sentences
    for the Word document indicated by the supplied path
    """
    
    myWord.Visible = False
    doc = myWord.Documents.Open(path)
    doc.TrackRevisions = False
    doc.ActiveWindow.View.RevisionsFilter.Markup = 2
    for table in doc.Tables:
        table.Delete()
    doc.Fields.Unlink()
    doc.Save()
    for omath in doc.OMaths:
        omath.Remove()
    
    #Generate sentence spans
    text = doc.Content.Text
    
    if tokenizer == "nltk":
        span_generator = sentence_tokenizer.span_tokenize(text)
        spans = list(span_generator)
    
    elif tokenizer == "spacy":
        nlp_doc = nlp(text)
        spans = [(s.start_char, s.end_char) for s in nlp_doc.sents]
    
    li = sorted([i for i in range(args.window)] + [i for i in range(args.window)])
    li.pop(0)
    window_sizes = [50 + ((-1)**i) * j for i, j in enumerate(li)]

    correct = False
    for window_size in window_sizes:
        if not correct:    

            #Calculate jump points in the Doc indices
            macro = myWord.Documents.Open(os.path.abspath("macro.docm"))
            result = myWord.Application.Run("CheckJumps", 
                                            path,
                                            window_size)
            jumps = json.loads(result)

            #Check for sentences with revised boundaries
            span_ends_string = json.dumps([reverse_index_conversion(e, jumps) for s, e in spans])
            macro = myWord.Documents.Open(os.path.abspath("macro.docm"))
            result = myWord.Application.Run("CheckBoundaryRevisions", 
                                            span_ends_string,
                                            path)
            joins = json.loads(result)

            if len(joins) > 0:
                if joins[-1] == len(spans) - 1:
                    joins.pop()

            #Join sentences with revised boundaries
            for join in joins[::-1]:
                spans = spans[:join] + [(spans[join][0], spans[join+1][1])] + spans[join+2:]

            correct = all([doc.Range(reverse_index_conversion(start, jumps), 
                                         reverse_index_conversion(end, jumps)).Text == text[start:end] for start, end in spans])
            if correct:
                tqdm.write("All sentences extracted with window size of {}".format(window_size))
    
    
    if correct:

        #Convert sentence spans to Doc indices and extract sentence pairs
        converted_spans = [(reverse_index_conversion(s, jumps), 
                            reverse_index_conversion(e, jumps)) for s, e in spans[::-1]]
        myWord.Visible = False
        macro = myWord.Documents.Open(os.path.abspath("macro.docm"))
        result = myWord.Application.Run("ExtractSentences", 
                                        json.dumps(converted_spans), 
                                        json.dumps(spans[::-1]),
                                        text,
                                        path)
        sentences = json.loads(result)
    else:
        sentences = {"OriginalSentences": [], "RevisedSentences": []}
        tqdm.write("Sentences not extracted window size range of {}; try increasing the window size range.".format(args.window))
        
    return sentences, len(spans)

def main():
    exclude_case_ids = []
    if args.reset:
        with open("sentences.tsv", 'w', encoding="utf-8") as out_file:
            tsv_writer = csv.writer(out_file, delimiter='\t')
            tsv_writer.writerow(["file", "original", "revised"])
    else:
        with open("buildSentenceDataset.log", 
                  'r', 
                  encoding="utf-8", 
                  errors='ignore') as file:
            lines = file.readlines()
        info_lines = [l for l in lines if l.split(":")[0] == "INFO"]
        incomplete_cases = []
        for line in info_lines:
            processed_match = re.search("O-20\d{2}-\d{6}", line)
            if processed_match is not None:
                #Include cases with incorrect number of sentences added during previous execution
                if args.correct:
                    correct_match = re.search("Added (\d+) of (\d+) sentences for (O-20\d{2}-\d{6})", line)
                    if correct_match is not None:
                        if int(correct_match.group(1)) == int(correct_match.group(2)):
                            exclude_case_ids.append(correct_match.group(3))
                #Exclude all previously processed sentences
                else:
                    exclude_case_ids.append(processed_match.group(0))
                
    myWord = Dispatch("Word.Application")
    myWord.Visible = True
    
    for file_name in tqdm(os.listdir(docs_path), ascii=True):
        myWord = Dispatch("Word.Application")
        if file_name[:13] not in exclude_case_ids:
            start = time.time()
            if args.verbose:
                tqdm.write(file_name)
            doc_path = os.path.join(docs_path, file_name)

            with open("sentences.tsv", 'at', encoding="utf-8") as out_file:
                tsv_writer = csv.writer(out_file, delimiter='\t')
                try:
                    sentences, total_num_sents = get_sentence_pairs(doc_path)
                    for original_sentence, revised_sentence in zip(sentences["OriginalSentences"][::-1], 
                                                                   sentences["RevisedSentences"][::-1]):
                        tsv_writer.writerow([file_name[:13],
                                             original_sentence.strip().encode('utf-8', 'replace').decode(),
                                             revised_sentence.strip().encode('utf-8', 'replace').decode()])
                    logger.info("Added {} of {} sentences for {}".format(len(sentences["OriginalSentences"]),
                                                                              total_num_sents,
                                                                              file_name))
                    if args.verbose:
                        tqdm.write("Extracted {} of {} sentence pairs;".format(len(sentences["OriginalSentences"]),
                                                                               total_num_sents))
                        if len(sentences["OriginalSentences"]) > 0:
                            sample = random.randint(0, len(sentences["OriginalSentences"]) - 1)
                            tqdm.write("Original: " + sentences["OriginalSentences"][sample])
                            tqdm.write("Revised: " + sentences["RevisedSentences"][sample])
                except pythoncom.com_error as e:
                    logger.error("COM error for {}: {}".format(file_name, str(e)))
                    tqdm.write(str(e))
                except json.decoder.JSONDecodeError as e:
                    logger.error("JSONDecodeError error for {}: {}".format(file_name, str(e)))
                    tqdm.write(str(e))
                if args.verbose:
                    tqdm.write("Execution time: {:.2f}".format(time.time() - start))
                    tqdm.write("=======================================")
                    tqdm.write("")
    
    myWord.Application.Quit()
    
if __name__ == "__main__":
    main()
