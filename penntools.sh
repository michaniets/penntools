#!/bin/bash

#### extract words from Penn parsed corpus (psd file)
####
#### run this script in the folder where the input psd files are
#### RNNTagger must be a sister folder
####
#### command line: for i in *.psd ; do penntools.sh $i > /dev/null ;done

#mcvf-lgermed-tmp
dir="220501-mcvf-ppchf-lgermed-psd"  # where the input psd files are
file=$1

echo "Extracting words (terminal nodes) from $file"
# This will produce
# - tmp-penntools-nodes   numbered words
# - tmp-penntools-tagme   words only (input to tagger)
# - one-word-per line format   to stdout
penntools.py -c 1 $file > tmp-${file%.*}.wpl

# Run tagger (any tagger, output needs to be one word per line, tab-delimited  (word-pos-lemma), e.g.
#pushd ~/tmp/RNNTagger 
#echo "Tagging $file RNN v1..."
#cut -f2 ../${dir}/tmp-penntools-tagme | cmd/my-rnn.sh > ../${dir}/tmp-tagged
#popd 

echo "Tagging $file RNN v2..."
pushd ~/tmp/OldFrenchTagger
my-rnn-of.sh ../${dir}/tmp-penntools-tagme > ../${dir}/tmp-tagged
popd

# Merge node number file with tagger output.   This will create 4 columns, e.g.: #14	ad VERcjg avoir
echo "Copying tagger output to psd file"
paste tmp-penntools-nodes tmp-tagged |cut -f1,3- > tmp-penntools-merge 
# Merge annotation with psd file 
penntools.py -m tmp-penntools-merge tmp-penntools-$file > rnn/$file
# cleanup
rm tmp-*


exit

for i in lemComp*.wpl
do
    t=`echo $i|sed -e s,lemComp,tagComp,`
    o=`echo $i|sed -e s,lemComp,comp,`
    o=`echo $o|sed -e s,\.lgermed,,`
    echo "$i -- $t -- $o"
    paste $i <(cut -f3-4 $t) | sed -e 's,\t<.*,,'|grep -v '<div ignore'|awk 'NF>0' > $o 
done
