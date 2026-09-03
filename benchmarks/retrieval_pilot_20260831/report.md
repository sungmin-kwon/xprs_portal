# XPRS retrieval pipeline pilot

Generated: 2026-08-31T06:37:47.953187+00:00

## Corpus

- Questions: 6
- Documents: 237
- Genes: 6
- Semantic Scholar requests: 12
- Embedding time: 79.46s

## Aggregate proxy metrics

Cross-encoder relevance is a shared diagnostic proxy, not independent ground truth. Use `blinded_review.csv` for a valid human comparison.

| Pipeline | Mean CE score | Any keyword | 2+ keywords | Mean retrieval ms | Mean rerank ms |
|---|---:|---:|---:|---:|---:|
| chroma_dense_10 | 0.670 | 90.0% | 68.3% | 7.7 | 0.0 |
| chroma_dense_30_rerank_10 | 0.802 | 93.3% | 71.7% | 7.6 | 6586.2 |
| lancedb_hybrid_30_rerank_10 | 0.802 | 95.0% | 71.7% | 36.6 | 2972.3 |

## CCND1: How does CCND1 amplification affect breast cancer prognosis and survival?

### chroma_dense_10

1. Impact of CCND1 amplification on the prognosis of hormone receptor–positive, HER2-negative breast cancer patients—correlation of clinical and pathological markers (CE=1.000, keywords=4, citations=7)
2. Prognostic and Predictive Value of CCND1/Cyclin D1 Amplification in Breast Cancer With a Focus on Postmenopausal Patients: A Systematic Review and Meta-Analysis (CE=0.998, keywords=4, citations=54)
3. CCND1 Amplification in Breast Cancer -associations With Proliferation, Histopathological Grade, Molecular Subtype and Prognosis (CE=0.998, keywords=2, citations=45)
4. CCND1 Amplification Contributes to Immunosuppression and Is Associated With a Poor Prognosis to Immune Checkpoint Inhibitors in Solid Tumors (CE=0.999, keywords=4, citations=70)
5. CCND1 Amplification Profiling Identifies a Subtype of Melanoma Associated With Poor Survival and an Immunosuppressive Tumor Microenvironment (CE=0.998, keywords=3, citations=21)

### chroma_dense_30_rerank_10

1. Impact of CCND1 amplification on the prognosis of hormone receptor–positive, HER2-negative breast cancer patients—correlation of clinical and pathological markers (CE=1.000, keywords=4, citations=7)
2. CCND1 Amplification Contributes to Immunosuppression and Is Associated With a Poor Prognosis to Immune Checkpoint Inhibitors in Solid Tumors (CE=0.999, keywords=4, citations=70)
3. Prognostic and Predictive Value of CCND1/Cyclin D1 Amplification in Breast Cancer With a Focus on Postmenopausal Patients: A Systematic Review and Meta-Analysis (CE=0.998, keywords=4, citations=54)
4. CCND1 Amplification in Breast Cancer -associations With Proliferation, Histopathological Grade, Molecular Subtype and Prognosis (CE=0.998, keywords=2, citations=45)
5. CCND1 Amplification Profiling Identifies a Subtype of Melanoma Associated With Poor Survival and an Immunosuppressive Tumor Microenvironment (CE=0.998, keywords=3, citations=21)

### lancedb_hybrid_30_rerank_10

1. Impact of CCND1 amplification on the prognosis of hormone receptor–positive, HER2-negative breast cancer patients—correlation of clinical and pathological markers (CE=1.000, keywords=4, citations=7)
2. CCND1 Amplification Contributes to Immunosuppression and Is Associated With a Poor Prognosis to Immune Checkpoint Inhibitors in Solid Tumors (CE=0.999, keywords=4, citations=70)
3. Prognostic and Predictive Value of CCND1/Cyclin D1 Amplification in Breast Cancer With a Focus on Postmenopausal Patients: A Systematic Review and Meta-Analysis (CE=0.998, keywords=4, citations=54)
4. CCND1 Amplification in Breast Cancer -associations With Proliferation, Histopathological Grade, Molecular Subtype and Prognosis (CE=0.998, keywords=2, citations=45)
5. CCND1 Amplification Profiling Identifies a Subtype of Melanoma Associated With Poor Survival and an Immunosuppressive Tumor Microenvironment (CE=0.998, keywords=3, citations=21)


## ESR1: How do ESR1 mutations contribute to tamoxifen or endocrine therapy resistance in breast cancer?

### chroma_dense_10

1. ESR1 mutation as an emerging clinical biomarker in metastatic hormone receptor-positive breast cancer (CE=1.000, keywords=4, citations=342)
2. Exploring the role of ESR1 mutations in metastatic hormone receptor-positive breast cancer T cell immune surveillance disruption (CE=0.994, keywords=3, citations=12)
3. ESR1 mutations are frequent in newly diagnosed metastatic and loco-regional recurrence of endocrine-treated breast cancer and carry worse prognosis (CE=1.000, keywords=4, citations=99)
4. ESR1 Mutations in Breast Cancer (CE=0.999, keywords=3, citations=212)
5. ESR1 Y537S and D538G mutations drive resistance to CDK4/6 inhibitors in estrogen receptor-positive breast cancer (CE=0.596, keywords=2, citations=14)

### chroma_dense_30_rerank_10

1. ESR1 mutations are frequent in newly diagnosed metastatic and loco-regional recurrence of endocrine-treated breast cancer and carry worse prognosis (CE=1.000, keywords=4, citations=99)
2. ESR1 mutation as an emerging clinical biomarker in metastatic hormone receptor-positive breast cancer (CE=1.000, keywords=4, citations=342)
3. ESR1 Mutations in Breast Cancer (CE=0.999, keywords=3, citations=212)
4. ESR1 mutant breast cancers show elevated basal cytokeratins and immune activation (CE=0.999, keywords=3, citations=44)
5. Hotspot ESR1 mutations are multimodal and contextual modulators of breast cancer metastasis (CE=0.998, keywords=3, citations=48)

### lancedb_hybrid_30_rerank_10

1. ESR1 mutations are frequent in newly diagnosed metastatic and loco-regional recurrence of endocrine-treated breast cancer and carry worse prognosis (CE=1.000, keywords=4, citations=99)
2. ESR1 mutation as an emerging clinical biomarker in metastatic hormone receptor-positive breast cancer (CE=1.000, keywords=4, citations=342)
3. ESR1 Mutations in Breast Cancer (CE=0.999, keywords=3, citations=212)
4. ESR1 mutant breast cancers show elevated basal cytokeratins and immune activation (CE=0.999, keywords=3, citations=44)
5. Hotspot ESR1 mutations are multimodal and contextual modulators of breast cancer metastasis (CE=0.998, keywords=3, citations=48)


## TOX3: What evidence links TOX3 variants to breast cancer susceptibility?

### chroma_dense_10

1. Association of the functional genetic variants of TOX3 gene with breast cancer in Iran: A case-control study (CE=0.574, keywords=2, citations=2)
2. TOX3 protein expression is correlated with pathological characteristics in breast cancer (CE=0.477, keywords=1, citations=15)
3. TOX3 is expressed in mammary ER+ epithelial cells and regulates ER target genes in luminal breast cancer (CE=0.704, keywords=1, citations=37)
4. Association between the TOX3 rs3803662 C>T polymorphism and recurrent miscarriage in a southern Chinese population (CE=0.916, keywords=2, citations=1)
5. Risk Association of TOX3 and MMP7 Gene Polymorphisms with Sporadic Breast Cancer in Mexican Women (CE=0.842, keywords=2, citations=6)

### chroma_dense_30_rerank_10

1. Genetic and Epigenetic Regulation of TOX3 Expression in Breast Cancer (CE=0.960, keywords=3, citations=28)
2. TOX3 regulates neural progenitor identity. (CE=0.927, keywords=1, citations=24)
3. Association between the TOX3 rs3803662 C>T polymorphism and recurrent miscarriage in a southern Chinese population (CE=0.916, keywords=2, citations=1)
4. Risk Association of TOX3 and MMP7 Gene Polymorphisms with Sporadic Breast Cancer in Mexican Women (CE=0.842, keywords=2, citations=6)
5. TOX3 Promotes Ovarian Estrogen Synthesis: An RNA-Sequencing and Network Study (CE=0.735, keywords=1, citations=9)

### lancedb_hybrid_30_rerank_10

1. Genetic and Epigenetic Regulation of TOX3 Expression in Breast Cancer (CE=0.960, keywords=3, citations=28)
2. TOX3 regulates neural progenitor identity. (CE=0.927, keywords=1, citations=24)
3. Association between the TOX3 rs3803662 C>T polymorphism and recurrent miscarriage in a southern Chinese population (CE=0.916, keywords=2, citations=1)
4. Risk Association of TOX3 and MMP7 Gene Polymorphisms with Sporadic Breast Cancer in Mexican Women (CE=0.842, keywords=2, citations=6)
5. TOX3 Promotes Ovarian Estrogen Synthesis: An RNA-Sequencing and Network Study (CE=0.735, keywords=1, citations=9)


## PSMB8: What role does PSMB8 play in antitumor immunity and breast cancer prognosis?

### chroma_dense_10

1. Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (CE=0.818, keywords=2, citations=5)
2. MRI-based machine learning reveals proteasome subunit PSMB8-mediated malignant glioma phenotypes through activating TGFBR1/2-SMAD2/3 axis (CE=0.913, keywords=1, citations=1)
3. Correction: Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (CE=0.162, keywords=0, citations=1)
4. Analysis on methylation and expression of PSMB8 and its correlation with immunity and immunotherapy in lung adenocarcinoma. (CE=0.721, keywords=3, citations=5)
5. Increased expression of the immunoproteasome subunits PSMB8 and PSMB9 by cancer cells correlate with better outcomes for triple-negative breast cancers (CE=0.897, keywords=1, citations=28)

### chroma_dense_30_rerank_10

1. Psmb8 inhibits mitochondrial fission and alleviates myocardial ischaemia/reperfusion injury by targeting Drp1 degradation (CE=0.965, keywords=0, citations=11)
2. MRI-based machine learning reveals proteasome subunit PSMB8-mediated malignant glioma phenotypes through activating TGFBR1/2-SMAD2/3 axis (CE=0.913, keywords=1, citations=1)
3. Increased expression of the immunoproteasome subunits PSMB8 and PSMB9 by cancer cells correlate with better outcomes for triple-negative breast cancers (CE=0.897, keywords=1, citations=28)
4. Tradeoff between metabolic i-proteasome addiction and immune evasion in triple-negative breast cancer (CE=0.881, keywords=4, citations=22)
5. Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (CE=0.818, keywords=2, citations=5)

### lancedb_hybrid_30_rerank_10

1. Psmb8 inhibits mitochondrial fission and alleviates myocardial ischaemia/reperfusion injury by targeting Drp1 degradation (CE=0.965, keywords=0, citations=11)
2. MRI-based machine learning reveals proteasome subunit PSMB8-mediated malignant glioma phenotypes through activating TGFBR1/2-SMAD2/3 axis (CE=0.913, keywords=1, citations=1)
3. Increased expression of the immunoproteasome subunits PSMB8 and PSMB9 by cancer cells correlate with better outcomes for triple-negative breast cancers (CE=0.897, keywords=1, citations=28)
4. Tradeoff between metabolic i-proteasome addiction and immune evasion in triple-negative breast cancer (CE=0.881, keywords=4, citations=22)
5. Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (CE=0.818, keywords=2, citations=5)


## ANO1: Does ANO1 promote breast cancer proliferation, invasion, migration, or metastasis?

### chroma_dense_10

1. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (CE=0.999, keywords=2, citations=27)
2. Calcium-activated chloride channel ANO1 promotes breast cancer progression by activating EGFR and CAMK signaling (CE=0.989, keywords=1, citations=302)
3. Prognostic significance of ANO1 expression in cancers (CE=0.978, keywords=1, citations=10)
4. ANO1‐Mediated Inhibition of Cancer Ferroptosis Confers Immunotherapeutic Resistance through Recruiting Cancer‐Associated Fibroblasts (CE=0.947, keywords=2, citations=59)
5. Promoter hypermethylation as a novel regulator of ANO1 expression and function in prostate cancer bone metastasis (CE=0.481, keywords=2, citations=4)

### chroma_dense_30_rerank_10

1. ANO1: central role and clinical significance in non-neoplastic and neoplastic diseases (CE=1.000, keywords=4, citations=15)
2. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (CE=0.999, keywords=2, citations=27)
3. ANO1 stabilizes partial EMT to drive colorectal cancer metastasis through PI3K/AKT/mTOR and ERK signaling pathways (CE=0.995, keywords=4, citations=1)
4. Calcium-activated chloride channel ANO1 promotes breast cancer progression by activating EGFR and CAMK signaling (CE=0.989, keywords=1, citations=302)
5. Synthesis and biological evaluation of novel Ani9 derivatives as potent and selective ANO1 inhibitors. (CE=0.979, keywords=3, citations=35)

### lancedb_hybrid_30_rerank_10

1. ANO1: central role and clinical significance in non-neoplastic and neoplastic diseases (CE=1.000, keywords=4, citations=15)
2. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (CE=0.999, keywords=2, citations=27)
3. ANO1 stabilizes partial EMT to drive colorectal cancer metastasis through PI3K/AKT/mTOR and ERK signaling pathways (CE=0.995, keywords=4, citations=1)
4. Calcium-activated chloride channel ANO1 promotes breast cancer progression by activating EGFR and CAMK signaling (CE=0.989, keywords=1, citations=302)
5. Synthesis and biological evaluation of novel Ani9 derivatives as potent and selective ANO1 inhibitors. (CE=0.979, keywords=3, citations=35)


## HLA-DRB1: Are HLA-DRB1 alleles associated with breast cancer susceptibility or immune response?

### chroma_dense_10

1. HLA-DRB1 alleles and cervical cancer: A meta-analysis of 36 case-control studies. (CE=0.482, keywords=2, citations=30)
2. Carriage of HLA-DRB1*11 and 1*12 alleles and risk factors in patients with breast cancer in Burkina Faso (CE=0.850, keywords=3, citations=9)
3. Breast Cancer Is Associated with Increased HLA-DRB1*11:01 and HLA-DRB1*10:01 Allele Frequency in a Population of Patients from Central Italy (CE=0.973, keywords=2, citations=10)
4. HLA-DRB1 alleles of susceptibility and protection in Iranians with autoimmune hepatitis. (CE=0.174, keywords=3, citations=24)
5. Alleles of HLA-DRB1*04 Associated with Pulmonary Tuberculosis in Amazon Brazilian Population (CE=0.265, keywords=3, citations=51)

### chroma_dense_30_rerank_10

1. Breast Cancer Is Associated with Increased HLA-DRB1*11:01 and HLA-DRB1*10:01 Allele Frequency in a Population of Patients from Central Italy (CE=0.973, keywords=2, citations=10)
2. Association of HLA-DRB1 amino acid residues with giant cell arteritis: genetic association study, meta-analysis and geo-epidemiological investigation (CE=0.919, keywords=4, citations=50)
3. Carriage of HLA-DRB1*11 and 1*12 alleles and risk factors in patients with breast cancer in Burkina Faso (CE=0.850, keywords=3, citations=9)
4. HLA-DRB1 and HLA-DQB1 Are Associated with Adult-Onset Immunodeficiency with Acquired Anti-Interferon-Gamma Autoantibodies (CE=0.688, keywords=1, citations=58)
5. Identification of HLA-DRB1 association to adalimumab immunogenicity (CE=0.657, keywords=2, citations=68)

### lancedb_hybrid_30_rerank_10

1. Breast Cancer Is Associated with Increased HLA-DRB1*11:01 and HLA-DRB1*10:01 Allele Frequency in a Population of Patients from Central Italy (CE=0.973, keywords=2, citations=10)
2. Association of HLA-DRB1 amino acid residues with giant cell arteritis: genetic association study, meta-analysis and geo-epidemiological investigation (CE=0.919, keywords=4, citations=50)
3. Carriage of HLA-DRB1*11 and 1*12 alleles and risk factors in patients with breast cancer in Burkina Faso (CE=0.850, keywords=3, citations=9)
4. HLA-DRB1 and HLA-DQB1 Are Associated with Adult-Onset Immunodeficiency with Acquired Anti-Interferon-Gamma Autoantibodies (CE=0.688, keywords=1, citations=58)
5. Identification of HLA-DRB1 association to adalimumab immunogenicity (CE=0.657, keywords=2, citations=68)
