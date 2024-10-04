# -*- coding: utf-8 -*-
"""Calculate Sponge Data.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1TSMPMUdRvnOaMQMeYrSd3gsK6yurbuQ0
"""

import sys
sys.path.append("./SimilarityRegression/")

import pandas as pd
import itertools
import os
import gzip
import glob

from tqdm.notebook import tqdm_notebook

from similarityregression import PairwiseAlignment as pwsaln
from similarityregression import AlignmentTools as alntools
from similarityregression import PredictSimilarity as srpred

matchOnlyMotifs = True

"""# Read Data

## Sponge
"""

# Collate Sponge Data
df_sponge = pd.read_table('Sponge/SpongeDomains.tab', header=None)
df_sponge.columns=['protein', 'tf', 'domain', 'start', 'end', 'seq', 'domain_order']
df_sponge.head()

dinc = []
for pid, pfeats in df_sponge.groupby('protein'):
    if pfeats.shape[0] > 1:
        mcopies = pfeats['start']
        dinc.append(mcopies.is_monotonic_increasing)

all(dinc)

print 'N proteins:', len(df_sponge['protein'].unique())
print 'N genes:', len(df_sponge['tf'].unique())

"""## Cis-BP"""

# 2.0
loc_DBFiles = 'REF/DB_2.00/'
domains = pd.read_csv(loc_DBFiles + 'domains.tab', sep = '\t', skiprows=[1], index_col=0)

tfs = pd.read_csv(loc_DBFiles + 'tfs.tab', sep = '\t', skiprows=[1], index_col=0)
tf_families = pd.read_csv(loc_DBFiles + 'tf_families.tab', sep = '\t', skiprows=[1], index_col=0)

motifs = pd.read_csv(loc_DBFiles + 'motifs.tab', sep = '\t', skiprows=[1], index_col=0)
motif_features = pd.read_csv(loc_DBFiles + 'motif_features.tab', sep = '\t', skiprows=[1], index_col=0)
motif_features['Pfam'] = [domains['Pfam_Name'].get(x) for x in motif_features['Domain_ID']]

proteins = pd.read_csv(loc_DBFiles + 'proteins.tab', sep = '\t', skiprows=[1], index_col=0)
prot_features = pd.read_csv(loc_DBFiles + 'prot_features.tab', sep = '\t', skiprows=[1], index_col=0)
prot_features['Pfam'] = [domains['Pfam_Name'].get(x) for x in prot_features['Domain_ID']]

sr_models = {}
# Collate SR Models (1.97d):
for loc_SRModel in glob.glob('REF/DB_1.97/SRModels/*json'):
    SRModel = srpred.ReadSRModel(loc_SRModel)
    if SRModel['Family_Name'] == 'NO_THRESHOLD':
        sr_models['NO_THRESHOLD'] = SRModel
    else:
        fid_2 = tf_families.reset_index().set_index('Family_Name')['Family_ID'].get(SRModel['Family_Name'])
        if fid_2 is not None:
            SRModel['Family_ID'] = fid_2
            sr_models[fid_2] = SRModel
        else:
            print('Warning missing:',SRModel)
sr_models

"""### Assign TF Families"""

Pfams2Fam = {}
for FID, info in tf_families.iterrows():
    DBDs = info['DBDs'].split(',')
    DBDs.sort()
    Pfams2Fam[tuple(DBDs)] = FID
Pfams2Fam

motif_features['Family_ID'] = ''
for mid, mdata in motif_features.groupby('Motif_ID'):
    m_pfams = list(set(mdata['Pfam']))
    m_pfams.sort()
    motif_features.loc[motif_features['Motif_ID'] == mid, 'Family_ID'] = Pfams2Fam.get(tuple(m_pfams))

df_sponge['Family_ID'] = ''
for mid, mdata in df_sponge.groupby('protein'):
    m_pfams = list(set(mdata['domain']))
    m_pfams.sort()
    df_sponge.loc[df_sponge['protein'] == mid, 'Family_ID'] = Pfams2Fam.get(tuple(m_pfams))

"""## Parse Domains For Alignment"""

# Check no new domains
set(df_sponge['domain']).isdisjoint(set(domains['Pfam_Name']))

# Collect Sequences & Run Alignment
for pfam_name in domains['Pfam_Name'].unique():
    DBDseqs = set()
    if matchOnlyMotifs is False:
        DBDseqs.update(set(prot_features.loc[prot_features['Pfam'] == pfam_name, 'ProtFeature_Sequence']))

    DBDseqs.update(set(motif_features.loc[motif_features['Pfam'] == pfam_name, 'MotifFeature_Sequence']))
    DBDseqs.update(set(df_sponge.loc[df_sponge['domain'] == pfam_name, 'seq']))

    if len(DBDseqs) > 0:
        with open('Domains/{}.fa'.format(pfam_name), 'w') as outfile:
            for DBDseq in DBDseqs:
                outfile.write('>' + DBDseq + '\n' + DBDseq + '\n')

        print(pfam_name)
        os.system('python RunAPHID.py REF/Pfam_HMMs/{}.hmm Domains/{}.fa semiglobal'.format(pfam_name, pfam_name))

#Read results into dictionary that maps the DBD sequence to its reference alignment
AlnDict_ByPfam = {} # Pfam : {Seq : Reference Alignment}
AlnLength_ByPfam = {}
for loc_aligned in glob.glob('DBDMatchPos_aphid/*matchpos_semiglobal.fa'):
    pfam_name = loc_aligned.split('/')[-1].split('.')[0]
    AlnDict_ByPfam[pfam_name] = {}
    lengths = []
    for seq, aln in alntools.FastaIter(fileloc=loc_aligned):
        AlnDict_ByPfam[pfam_name][seq] = aln.upper().replace('.', '-')
        lengths.append(len(aln))
    if all([x == lengths[0] for x in lengths]):
        AlnLength_ByPfam[pfam_name] = lengths[0]
    else:
        print('Variable Alignment Length', pfam_name)

len(motif_features.groupby(['Pfam', 'MotifFeature_Sequence'])) + len(df_sponge.groupby(['domain', 'seq']))

SR_Scores_i = []
SR_Scores = []

for tf_family, fdata in tf_families.iterrows():
    DBDs = fdata['DBDs'].split(',')
    if tf_family in set(df_sponge['Family_ID']):
        # Get SR Model
        SRModel_family = sr_models.get(tf_family)
        if SRModel_family is None:
            SRModel_family = sr_models.get('NO_THRESHOLD')
            print tf_family, fdata['Family_Name'], DBDs, 'NO_THRESHOLD'
        else:
            print tf_family, fdata['Family_Name'], DBDs, SRModel_family['Model.Class']

        JointSeqDict = {}
        for currentDBD in DBDs:
            currentDBD_dict = AlnDict_ByPfam[currentDBD].copy()
            for unaln, aln in currentDBD_dict.items():
                jointaln = '' # has to be in order of the family name
                for DBD in DBDs:
                    if DBD == currentDBD:
                        jointaln += aln
                    else:
                        jointaln += '-'*AlnLength_ByPfam[DBD]
                JointSeqDict[unaln] = jointaln

        # Motifs
        MotifSequences = {} # MID: [DBD Sequences]
        for motif_id, MID_mfeats in motif_features[motif_features['Family_ID'] == tf_family].groupby('Motif_ID'):
            alnseqs = []
            for ID_mfeat, mfeat in MID_mfeats.iterrows():
                unaln = mfeat['MotifFeature_Sequence']
                aln = JointSeqDict[unaln]
                alnseqs.append(aln)
            MotifSequences[motif_id] = ','.join(alnseqs)

        # Sponge Proteins
        ProteinSequences = {} # Sponge: [DBD Sequences]
        for protein, MID_mfeats in df_sponge[df_sponge['Family_ID'] == tf_family].groupby('protein'):
            alnseqs = []
            for ID_mfeat, mfeat in MID_mfeats.iterrows():
                unaln = mfeat['seq']
                aln = JointSeqDict[unaln]
                alnseqs.append(aln)
            ProteinSequences[protein] = ','.join(alnseqs)

        # Flipped Dict
        uSeqs = {} # seq : [id, id, id]
        for key, seq in MotifSequences.items():
            if seq in uSeqs:
                uSeqs[seq].add(key)
            else:
                uSeqs[seq] = set([key])
        for key, seq in ProteinSequences.items():
            if seq in uSeqs:
                uSeqs[seq].add(key)
            else:
                uSeqs[seq] = set([key])

        # Score Against itself (e.g. identical)
        for uSeq, ids in tqdm_notebook(uSeqs.items()):
            l_ids = list(ids)
            l_ids.sort()
            sr_alignment = pwsaln.AlignDBDArrays(('i', uSeq.split(',')),
                                                 ('j', uSeq.split(',')))
            SR_Score, SR_Class = srpred.ScoreAlignmentResult(resultDict=sr_alignment, scoreDict=SRModel_family)
            for i, j in itertools.combinations(l_ids, 2):
                pair = [i, j]
                SR_Scores_i.append(tuple([tf_family] + pair))
                SR_Scores.append([sr_alignment['PctID_L'], SR_Score, SR_Class, SRModel_family['Model.Class'], SRModel_family['Family_Name'] ,fdata['Family_Name']])


        #Score unique seq x seq
        combos = [i for i in itertools.combinations(uSeqs.keys(), 2)]
        for i, j in tqdm_notebook(combos):
            ids_i = list(uSeqs[i])
            ids_j = list(uSeqs[j])
            sr_alignment = pwsaln.AlignDBDArrays(('|'.join(ids_i), i.split(',')),
                                                 ('|'.join(ids_j), j.split(',')))
            SR_Score, SR_Class = srpred.ScoreAlignmentResult(resultDict=sr_alignment, scoreDict=SRModel_family)
            for id_i in ids_i:
                for id_j in ids_j:
                    pair = [id_i, id_j]
                    pair.sort()
                    SR_Scores_i.append(tuple([tf_family] + pair))
                    SR_Scores.append([sr_alignment['PctID_L'], SR_Score, SR_Class, SRModel_family['Model.Class'], SRModel_family['Family_Name'] ,fdata['Family_Name']])



#         # Do Motif x Motif Alignments
#         print('Aligning Motifs x Motifs')
#         mkeys = MotifSequences.keys()
#         mkeys.sort()
#         for i, j in itertools.combinations(mkeys, 2):
#             sr_alignment = pwsaln.AlignDBDArrays((i, MotifSequences[i]),
#                                                  (j, MotifSequences[j]))
#             SR_Score, SR_Class = srpred.ScoreAlignmentResult(resultDict=sr_alignment, scoreDict=SRModel_family)
#             SR_Scores_i.append((tf_family, i, j))
#             SR_Scores.append([sr_alignment['PctID_L'], SR_Score, SR_Class, SRModel_family['Model.Class'], SRModel_family['Family_Name'] ,fdata['Family_Name']])

#         # Do Motif x Sponge Alignments
#         print('Aligning Motifs x Sponge Proteins')
#         pkeys = ProteinSequences.keys()
#         pkeys.sort()
#         for mid in mkeys:
#             for pid in pkeys:
#                 sr_alignment = pwsaln.AlignDBDArrays((mid, MotifSequences[mid]),
#                                                      (pid, ProteinSequences[pid]))
#                 SR_Score, SR_Class = srpred.ScoreAlignmentResult(resultDict=sr_alignment, scoreDict=SRModel_family)
#                 SR_Scores_i.append((tf_family, mid, mid))
#                 SR_Scores.append([sr_alignment['PctID_L'], SR_Score, SR_Class, SRModel_family['Model.Class'], SRModel_family['Family_Name'] ,fdata['Family_Name']])

#         # Do Sponge x Sponge Alignments
#         print('Aligning Sponge x Sponge Proteins')
#         for i, j in itertools.combinations(pkeys, 2):
#             sr_alignment = pwsaln.AlignDBDArrays((i, ProteinSequences[i]),
#                                                  (j, ProteinSequences[j]))
#             SR_Score, SR_Class = srpred.ScoreAlignmentResult(resultDict=sr_alignment, scoreDict=SRModel_family)
#             SR_Scores_i.append((tf_family, i, j))
#             SR_Scores.append([sr_alignment['PctID_L'], SR_Score, SR_Class, SRModel_family['Model.Class'], SRModel_family['Family_Name'] ,fdata['Family_Name']])

SR_Scores = pd.DataFrame(SR_Scores, columns=['AA %ID', 'SR_Score', 'SR_Class', 'SRModel_Class', 'SRModel_Name', 'Family_Name',])
SR_Scores.index = pd.MultiIndex.from_tuples(SR_Scores_i)
SR_Scores.index.names = ['Family_ID', 'ID_x', 'ID_y']
# Sort the DF
SR_Scores = SR_Scores.reset_index()
SR_Scores = SR_Scores.sort_values(['Family_ID', 'SR_Score', 'ID_x', 'ID_y'], ascending=[True, False, True, True])

# Display Output
SR_Scores.to_csv('SR_Sponge_All.csv.gz', compression='gzip')
SR_Scores.head()

# Sponge -> Motif Inferences
i_Sponge = SR_Scores['ID_x'].isin(df_sponge['protein']) | SR_Scores['ID_y'].isin(df_sponge['protein'])
i_Motif = SR_Scores['ID_x'].str.endswith('_2.00') | SR_Scores['ID_y'].str.endswith('_2.00')
Sponge_MotifInferences = SR_Scores[i_Sponge & i_Motif]
Sponge_MotifInferences = Sponge_MotifInferences.rename({'ID_x' : 'Motif_ID', 'ID_y' : 'Strongylocentrotus_Protein'}, axis = 1)

p2tf = { x[1]: x[2] for x in df_sponge[['protein','tf']].drop_duplicates().itertuples()}
Sponge_MotifInferences['Strongylocentrotus_TF'] = [p2tf.get(x) for x in Sponge_MotifInferences['Strongylocentrotus_Protein']]
Sponge_MotifInferences['Motif.TF_ID'] = [motifs['TF_ID'].get(x) for x in Sponge_MotifInferences['Motif_ID']]
Sponge_MotifInferences = pd.merge(Sponge_MotifInferences,
                                    tfs[['TF_Species','DBID', 'TF_Name']].rename({'TF_Species' : 'Motif.Species', 'DBID' : 'Motif.TF_DBID', 'TF_Name': 'Motif.TF_Name'}, axis = 1),
                                    how = 'left',
                                    left_on='Motif.TF_ID', right_index=True)
Sponge_MotifInferences.to_csv('Strongylocentrotus_MotifInferences.csv.gz', compression='gzip')
Sponge_MotifInferences.head()

motif_x_motif[(motif_x_motif['SRModel_Name'] == 'Homeodomain,POU')].sample(n=10)

for x in Sponge_MotifInferences.columns:
    print(x)

Sponge_MotifInferences[Sponge_MotifInferences['Strongylocentrotus_TF'].isnull()]



df_sponge[df_sponge['protein'] == 'XP_030828650.1']

p2tf.get('XP_030828650.1')



