#!/bin/bash

#### wrapper script for penntools.py and RNN tagger
####
#### extract words from Penn parsed corpus (psd file)
####
#### run this script in the folder where the input psd files are
#### RNNTagger must be a sister folder
####
#### command line: for i in *.psd ; do penntools.sh $i > /dev/null ;done

file=$1
tagger=$2
python=penntools.py
pypath=/Users/Shared/silpac/git/penntools

if [ ! -x "$2" ] || [ ! -f $1 ]
then
    echo "file(s) not found: argument1 needs to be the input file"
    echo "                   argument2 needs to be the tagging script (executable)"
    exit 1
fi

## on julienas: add path of penntools git repo 
if [ ! -x "$python" ] 
then python=$pypath/$python
     if [ ! -x "$python" ] 
     then
	 echo "Script ${python} not found"
	 exit 1
     else
	 echo "Using script ${python}"
     fi
fi


tagger_dir=`dirname $2`
input_file=`basename $1`
cd `dirname $1`
corpus_dir=`pwd` # "220501-mcvf-ppchf-lgermed-psd"  # where the input psd files are
output_dir=rnn_output

echo "Extracting words (terminal nodes) from $file"
# This will produce
# - tmp-penntools-nodes   numbered words
# - tmp-penntools-tagme   words only (input to tagger)
# - one-word-per line format   to stdout
cd $corpus_dir
#penntools.py -c 1 $file > tmp-${file%.*}.wpl
${python} -c 1 "$input_file" > tmp-$input_file.wpl

# Run tagger (any tagger, output needs to be one word per line, tab-delimited  (word-pos-lemma), e.g.
echo "Tagging and lemmatizing: $input_file"
cd $tagger_dir
./my-rnn-of.sh ${corpus_dir}/tmp-penntools-tagme > ${corpus_dir}/tmp-tagged

cd $corpus_dir
if [ ! -d $output_dir ]; then echo "creating output folder: $output_dir"; mkdir $output_dir; fi
# Merge node number file with tagger output. Creates 4 columns, e.g.: #14 ad VERcjg avoir
echo "Copying tagger output to psd file"
paste tmp-penntools-nodes tmp-tagged |cut -f1,3- > tmp-penntools-merge 
# Merge annotation with psd file 
${python} -m tmp-penntools-merge tmp-penntools-$input_file > $output_dir/$input_file
# cleanup
rm tmp-*
echo "Finished writing $corpus_dir/$output_dir/$input_file"

exit
