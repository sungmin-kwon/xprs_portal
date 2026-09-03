# XPRS reranker comparison

Generated: 2026-08-31T07:41:00.919272+00:00

All rerankers received the same BGE-M3 dense top-30 candidates. Scores are not compared across models because their calibrations differ.

## Aggregate results

| Model | Mean latency | Disease mention @1 | Disease in title @1 | Target nDCG@10 | Primary nDCG@10 | Other-disease nDCG@10 | Korean nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bge_base_control | 3.06s | 72.7% | 63.6% | 0.706 | 0.713 | 0.694 | 0.746 |
| medcpt | 2.92s | 100.0% | 72.7% | 0.920 | 0.944 | 0.879 | 0.925 |
| bge_v2_m3 | 9.36s | 100.0% | 72.7% | 0.860 | 0.846 | 0.885 | 0.916 |
| qwen3_0_6b | 31.01s | 72.7% | 72.7% | 0.852 | 0.883 | 0.797 | 0.721 |

## ccnd1_breast_prognosis_en

How does CCND1 amplification affect breast cancer prognosis and survival?

### bge_base_control (3.23s)

1. Impact of CCND1 amplification on the prognosis of hormone receptor–positive, HER2-negative breast cancer patients—correlation of clinical and pathological markers (target, keywords=4)
2. CCND1 Amplification Contributes to Immunosuppression and Is Associated With a Poor Prognosis to Immune Checkpoint Inhibitors in Solid Tumors (non-target, keywords=4)
3. Prognostic and Predictive Value of CCND1/Cyclin D1 Amplification in Breast Cancer With a Focus on Postmenopausal Patients: A Systematic Review and Meta-Analysis (target, keywords=4)
4. CCND1 Amplification in Breast Cancer -associations With Proliferation, Histopathological Grade, Molecular Subtype and Prognosis (target, keywords=2)
5. CCND1 Amplification Profiling Identifies a Subtype of Melanoma Associated With Poor Survival and an Immunosuppressive Tumor Microenvironment (non-target, keywords=3)

### medcpt (2.86s)

1. Prognostic and Predictive Value of CCND1/Cyclin D1 Amplification in Breast Cancer With a Focus on Postmenopausal Patients: A Systematic Review and Meta-Analysis (target, keywords=4)
2. Impact of CCND1 amplification on the prognosis of hormone receptor–positive, HER2-negative breast cancer patients—correlation of clinical and pathological markers (target, keywords=4)
3. CCND1 Amplification in Breast Cancer -associations With Proliferation, Histopathological Grade, Molecular Subtype and Prognosis (target, keywords=2)
4. CCND1 Copy Number Variation in Circulating Tumor DNA from Luminal B Breast Cancer Patients (target, keywords=2)
5. CCND1 Amplification Contributes to Immunosuppression and Is Associated With a Poor Prognosis to Immune Checkpoint Inhibitors in Solid Tumors (non-target, keywords=4)

### bge_v2_m3 (8.65s)

1. Impact of CCND1 amplification on the prognosis of hormone receptor–positive, HER2-negative breast cancer patients—correlation of clinical and pathological markers (target, keywords=4)
2. Prognostic and Predictive Value of CCND1/Cyclin D1 Amplification in Breast Cancer With a Focus on Postmenopausal Patients: A Systematic Review and Meta-Analysis (target, keywords=4)
3. CCND1 Amplification in Breast Cancer -associations With Proliferation, Histopathological Grade, Molecular Subtype and Prognosis (target, keywords=2)
4. CCND1 Copy Number Variation in Circulating Tumor DNA from Luminal B Breast Cancer Patients (target, keywords=2)
5. CCND1 Amplification Contributes to Immunosuppression and Is Associated With a Poor Prognosis to Immune Checkpoint Inhibitors in Solid Tumors (non-target, keywords=4)

### qwen3_0_6b (29.92s)

1. Prognostic and Predictive Value of CCND1/Cyclin D1 Amplification in Breast Cancer With a Focus on Postmenopausal Patients: A Systematic Review and Meta-Analysis (target, keywords=4)
2. Impact of CCND1 amplification on the prognosis of hormone receptor–positive, HER2-negative breast cancer patients—correlation of clinical and pathological markers (target, keywords=4)
3. CCND1 Copy Number Variation in Circulating Tumor DNA from Luminal B Breast Cancer Patients (target, keywords=2)
4. CCND1 Amplification in Breast Cancer -associations With Proliferation, Histopathological Grade, Molecular Subtype and Prognosis (target, keywords=2)
5. CCND1 Amplification Contributes to Immunosuppression and Is Associated With a Poor Prognosis to Immune Checkpoint Inhibitors in Solid Tumors (non-target, keywords=4)


## esr1_breast_resistance_en

How do ESR1 mutations contribute to tamoxifen or endocrine therapy resistance in breast cancer?

### bge_base_control (2.90s)

1. ESR1 mutations are frequent in newly diagnosed metastatic and loco-regional recurrence of endocrine-treated breast cancer and carry worse prognosis (target, keywords=4)
2. ESR1 mutation as an emerging clinical biomarker in metastatic hormone receptor-positive breast cancer (target, keywords=4)
3. ESR1 Mutations in Breast Cancer (target, keywords=3)
4. ESR1 mutant breast cancers show elevated basal cytokeratins and immune activation (target, keywords=3)
5. Hotspot ESR1 mutations are multimodal and contextual modulators of breast cancer metastasis (target, keywords=3)

### medcpt (3.16s)

1. ESR1 mutation as an emerging clinical biomarker in metastatic hormone receptor-positive breast cancer (target, keywords=4)
2. ESR1 Mutations in Breast Cancer (target, keywords=3)
3. The Clinical Utility of ESR1 Mutations in Hormone Receptor-Positive, HER2-Negative Advanced Breast Cancer. (target, keywords=3)
4. ESR1 activating mutations: From structure to clinical application (target, keywords=2)
5. ESR1 fusions and therapeutic resistance in metastatic breast cancer (target, keywords=3)

### bge_v2_m3 (9.97s)

1. ESR1 mutation as an emerging clinical biomarker in metastatic hormone receptor-positive breast cancer (target, keywords=4)
2. ESR1 mutations are frequent in newly diagnosed metastatic and loco-regional recurrence of endocrine-treated breast cancer and carry worse prognosis (target, keywords=4)
3. ESR1 Mutations in Breast Cancer (target, keywords=3)
4. ESR1 testing on FFPE samples from metastatic lesions in HR + /HER2- breast cancer after progression on CDK4/6 inhibitor therapy (target, keywords=3)
5. CDK4/6 Inhibitors Overcome Endocrine ESR1 Mutation-Related Resistance in Metastatic Breast Cancer Patients (target, keywords=4)

### qwen3_0_6b (40.05s)

1. The Clinical Utility of ESR1 Mutations in Hormone Receptor-Positive, HER2-Negative Advanced Breast Cancer. (target, keywords=3)
2. ESR1 Mutations in Breast Cancer (target, keywords=3)
3. ESR1 mutation as an emerging clinical biomarker in metastatic hormone receptor-positive breast cancer (target, keywords=4)
4. Primary endocrine resistance of ER+ breast cancer with ESR1 mutations interrogated by droplet digital PCR (target, keywords=3)
5. ESR1 mutations are frequent in newly diagnosed metastatic and loco-regional recurrence of endocrine-treated breast cancer and carry worse prognosis (target, keywords=4)


## tox3_breast_risk_en

What evidence links TOX3 variants to breast cancer susceptibility?

### bge_base_control (2.50s)

1. Genetic and Epigenetic Regulation of TOX3 Expression in Breast Cancer (target, keywords=3)
2. TOX3 regulates neural progenitor identity. (target, keywords=1)
3. Association between the TOX3 rs3803662 C>T polymorphism and recurrent miscarriage in a southern Chinese population (target, keywords=2)
4. Risk Association of TOX3 and MMP7 Gene Polymorphisms with Sporadic Breast Cancer in Mexican Women (target, keywords=2)
5. TOX3 Promotes Ovarian Estrogen Synthesis: An RNA-Sequencing and Network Study (target, keywords=1)

### medcpt (2.47s)

1. Genetic and Epigenetic Regulation of TOX3 Expression in Breast Cancer (target, keywords=3)
2. Association of the functional genetic variants of TOX3 gene with breast cancer in Iran: A case-control study (target, keywords=2)
3. The breast cancer susceptibility-related polymorphisms at the TOX3/LOC643714 locus associated with lung cancer risk in a Han Chinese population (target, keywords=3)
4. TOX3 protein expression is correlated with pathological characteristics in breast cancer (target, keywords=1)
5. Risk Association of TOX3 and MMP7 Gene Polymorphisms with Sporadic Breast Cancer in Mexican Women (target, keywords=2)

### bge_v2_m3 (7.99s)

1. Genetic and Epigenetic Regulation of TOX3 Expression in Breast Cancer (target, keywords=3)
2. Association between the TOX3 rs3803662 C>T polymorphism and recurrent miscarriage in a southern Chinese population (target, keywords=2)
3. TOX3 is expressed in mammary ER+ epithelial cells and regulates ER target genes in luminal breast cancer (target, keywords=1)
4. The breast cancer susceptibility-related polymorphisms at the TOX3/LOC643714 locus associated with lung cancer risk in a Han Chinese population (target, keywords=3)
5. Risk Association of TOX3 and MMP7 Gene Polymorphisms with Sporadic Breast Cancer in Mexican Women (target, keywords=2)

### qwen3_0_6b (22.55s)

1. Risk Association of TOX3 and MMP7 Gene Polymorphisms with Sporadic Breast Cancer in Mexican Women (target, keywords=2)
2. Genetic and Epigenetic Regulation of TOX3 Expression in Breast Cancer (target, keywords=3)
3. Association of the functional genetic variants of TOX3 gene with breast cancer in Iran: A case-control study (target, keywords=2)
4. TOX3 protein expression is correlated with pathological characteristics in breast cancer (target, keywords=1)
5. TOX3 is expressed in mammary ER+ epithelial cells and regulates ER target genes in luminal breast cancer (target, keywords=1)


## psmb8_breast_immunity_en

What role does PSMB8 play in antitumor immunity and breast cancer prognosis?

### bge_base_control (2.89s)

1. Psmb8 inhibits mitochondrial fission and alleviates myocardial ischaemia/reperfusion injury by targeting Drp1 degradation (non-target, keywords=0)
2. MRI-based machine learning reveals proteasome subunit PSMB8-mediated malignant glioma phenotypes through activating TGFBR1/2-SMAD2/3 axis (non-target, keywords=1)
3. Increased expression of the immunoproteasome subunits PSMB8 and PSMB9 by cancer cells correlate with better outcomes for triple-negative breast cancers (target, keywords=1)
4. Tradeoff between metabolic i-proteasome addiction and immune evasion in triple-negative breast cancer (target, keywords=4)
5. Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (non-target, keywords=2)

### medcpt (3.09s)

1. Increased expression of the immunoproteasome subunits PSMB8 and PSMB9 by cancer cells correlate with better outcomes for triple-negative breast cancers (target, keywords=1)
2. Tradeoff between metabolic i-proteasome addiction and immune evasion in triple-negative breast cancer (target, keywords=4)
3. Novel immune-related prognostic model and nomogram for breast cancer based on ssGSEA (target, keywords=2)
4. Expression of immunoproteasome genes is regulated by cell-intrinsic and –extrinsic factors in human cancers (target, keywords=2)
5. Correction: Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (non-target, keywords=0)

### bge_v2_m3 (10.06s)

1. Increased expression of the immunoproteasome subunits PSMB8 and PSMB9 by cancer cells correlate with better outcomes for triple-negative breast cancers (target, keywords=1)
2. Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (non-target, keywords=2)
3. MRI-based machine learning reveals proteasome subunit PSMB8-mediated malignant glioma phenotypes through activating TGFBR1/2-SMAD2/3 axis (non-target, keywords=1)
4. Tradeoff between metabolic i-proteasome addiction and immune evasion in triple-negative breast cancer (target, keywords=4)
5. Long non-coding RNA PSMB8-AS1 as a potential biomarker for postoperative recurrence in patients with Fuhrman grades 1–3 clear cell renal cell carcinoma (non-target, keywords=2)

### qwen3_0_6b (36.51s)

1. Correction: Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (non-target, keywords=0)
2. Increased expression of the immunoproteasome subunits PSMB8 and PSMB9 by cancer cells correlate with better outcomes for triple-negative breast cancers (target, keywords=1)
3. Tradeoff between metabolic i-proteasome addiction and immune evasion in triple-negative breast cancer (target, keywords=4)
4. Analysis on methylation and expression of PSMB8 and its correlation with immunity and immunotherapy in lung adenocarcinoma. (non-target, keywords=3)
5. Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (non-target, keywords=2)


## ano1_breast_progression_en

Does ANO1 promote breast cancer proliferation, invasion, migration, or metastasis?

### bge_base_control (2.85s)

1. ANO1: central role and clinical significance in non-neoplastic and neoplastic diseases (target, keywords=4)
2. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (non-target, keywords=2)
3. ANO1 stabilizes partial EMT to drive colorectal cancer metastasis through PI3K/AKT/mTOR and ERK signaling pathways (non-target, keywords=4)
4. Calcium-activated chloride channel ANO1 promotes breast cancer progression by activating EGFR and CAMK signaling (target, keywords=1)
5. Synthesis and biological evaluation of novel Ani9 derivatives as potent and selective ANO1 inhibitors. (non-target, keywords=3)

### medcpt (2.37s)

1. ANO1: central role and clinical significance in non-neoplastic and neoplastic diseases (target, keywords=4)
2. Calcium-activated chloride channel ANO1 promotes breast cancer progression by activating EGFR and CAMK signaling (target, keywords=1)
3. Synthesis and biological evaluation of novel Ani9 derivatives as potent and selective ANO1 inhibitors. (non-target, keywords=3)
4. Prognostic significance of ANO1 expression in cancers (target, keywords=1)
5. Cell-specific regulation of proliferation by Ano1/TMEM16A in breast cancer with different ER, PR, and HER2 status (target, keywords=1)

### bge_v2_m3 (9.07s)

1. ANO1: central role and clinical significance in non-neoplastic and neoplastic diseases (target, keywords=4)
2. Synthesis and biological evaluation of novel Ani9 derivatives as potent and selective ANO1 inhibitors. (non-target, keywords=3)
3. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (non-target, keywords=2)
4. Calcium-activated chloride channel ANO1 promotes breast cancer progression by activating EGFR and CAMK signaling (target, keywords=1)
5. Cell-specific regulation of proliferation by Ano1/TMEM16A in breast cancer with different ER, PR, and HER2 status (target, keywords=1)

### qwen3_0_6b (24.30s)

1. Synthesis and biological evaluation of novel Ani9 derivatives as potent and selective ANO1 inhibitors. (non-target, keywords=3)
2. Calcium-activated chloride channel ANO1 promotes breast cancer progression by activating EGFR and CAMK signaling (target, keywords=1)
3. Cell-specific regulation of proliferation by Ano1/TMEM16A in breast cancer with different ER, PR, and HER2 status (target, keywords=1)
4. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (non-target, keywords=2)
5. Ano1/TMEM16A Overexpression Is Associated with Good Prognosis in PR-Positive or HER2-Negative Breast Cancer Patients following Tamoxifen Treatment (target, keywords=0)


## hla_drb1_breast_risk_en

Are HLA-DRB1 alleles associated with breast cancer susceptibility or immune response?

### bge_base_control (2.83s)

1. Breast Cancer Is Associated with Increased HLA-DRB1*11:01 and HLA-DRB1*10:01 Allele Frequency in a Population of Patients from Central Italy (target, keywords=2)
2. Association of HLA-DRB1 amino acid residues with giant cell arteritis: genetic association study, meta-analysis and geo-epidemiological investigation (non-target, keywords=4)
3. Carriage of HLA-DRB1*11 and 1*12 alleles and risk factors in patients with breast cancer in Burkina Faso (target, keywords=3)
4. HLA-DRB1 and HLA-DQB1 Are Associated with Adult-Onset Immunodeficiency with Acquired Anti-Interferon-Gamma Autoantibodies (non-target, keywords=1)
5. Identification of HLA-DRB1 association to adalimumab immunogenicity (non-target, keywords=2)

### medcpt (3.18s)

1. Carriage of HLA-DRB1*11 and 1*12 alleles and risk factors in patients with breast cancer in Burkina Faso (target, keywords=3)
2. Breast Cancer Is Associated with Increased HLA-DRB1*11:01 and HLA-DRB1*10:01 Allele Frequency in a Population of Patients from Central Italy (target, keywords=2)
3. HLA-DRB1 Gene (non-target, keywords=1)
4. A transplantable tumor model allowing investigation of NY-BR-1-specific T cell responses in HLA-DRB1*0401 transgenic mice (target, keywords=1)
5. HLA-DRB1 alleles and cervical cancer: A meta-analysis of 36 case-control studies. (non-target, keywords=2)

### bge_v2_m3 (10.17s)

1. Carriage of HLA-DRB1*11 and 1*12 alleles and risk factors in patients with breast cancer in Burkina Faso (target, keywords=3)
2. Breast Cancer Is Associated with Increased HLA-DRB1*11:01 and HLA-DRB1*10:01 Allele Frequency in a Population of Patients from Central Italy (target, keywords=2)
3. A transplantable tumor model allowing investigation of NY-BR-1-specific T cell responses in HLA-DRB1*0401 transgenic mice (target, keywords=1)
4. HLA-DRB1 alleles and cervical cancer: A meta-analysis of 36 case-control studies. (non-target, keywords=2)
5. HLA-DRB1 Gene (non-target, keywords=1)

### qwen3_0_6b (35.90s)

1. Breast Cancer Is Associated with Increased HLA-DRB1*11:01 and HLA-DRB1*10:01 Allele Frequency in a Population of Patients from Central Italy (target, keywords=2)
2. Carriage of HLA-DRB1*11 and 1*12 alleles and risk factors in patients with breast cancer in Burkina Faso (target, keywords=3)
3. HLA-DRB1 alleles and cervical cancer: A meta-analysis of 36 case-control studies. (non-target, keywords=2)
4. A transplantable tumor model allowing investigation of NY-BR-1-specific T cell responses in HLA-DRB1*0401 transgenic mice (target, keywords=1)
5. HLA-DRB1 alleles of susceptibility and protection in Iranians with autoimmune hepatitis. (non-target, keywords=3)


## ano1_colorectal_en

What evidence links ANO1 to colorectal cancer progression or metastasis?

### bge_base_control (3.28s)

1. ANO1: central role and clinical significance in non-neoplastic and neoplastic diseases (non-target, keywords=3)
2. ANO1 stabilizes partial EMT to drive colorectal cancer metastasis through PI3K/AKT/mTOR and ERK signaling pathways (target, keywords=4)
3. Prognostic significance of ANO1 expression in cancers (target, keywords=3)
4. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (non-target, keywords=2)
5. ANO1‐Mediated Inhibition of Cancer Ferroptosis Confers Immunotherapeutic Resistance through Recruiting Cancer‐Associated Fibroblasts (non-target, keywords=3)

### medcpt (2.52s)

1. ANO1 stabilizes partial EMT to drive colorectal cancer metastasis through PI3K/AKT/mTOR and ERK signaling pathways (target, keywords=4)
2. Prognostic significance of ANO1 expression in cancers (target, keywords=3)
3. ANO1‐Mediated Inhibition of Cancer Ferroptosis Confers Immunotherapeutic Resistance through Recruiting Cancer‐Associated Fibroblasts (non-target, keywords=3)
4. ANO1: central role and clinical significance in non-neoplastic and neoplastic diseases (non-target, keywords=3)
5. Blockade of calcium-activated chloride channel ANO1 ameliorates ionizing radiation-induced intestinal injury (non-target, keywords=0)

### bge_v2_m3 (8.82s)

1. Prognostic significance of ANO1 expression in cancers (target, keywords=3)
2. ANO1 stabilizes partial EMT to drive colorectal cancer metastasis through PI3K/AKT/mTOR and ERK signaling pathways (target, keywords=4)
3. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (non-target, keywords=2)
4. ANO1: central role and clinical significance in non-neoplastic and neoplastic diseases (non-target, keywords=3)
5. Promoter hypermethylation as a novel regulator of ANO1 expression and function in prostate cancer bone metastasis (non-target, keywords=2)

### qwen3_0_6b (26.30s)

1. ANO1 stabilizes partial EMT to drive colorectal cancer metastasis through PI3K/AKT/mTOR and ERK signaling pathways (target, keywords=4)
2. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (non-target, keywords=2)
3. ANO1‐Mediated Inhibition of Cancer Ferroptosis Confers Immunotherapeutic Resistance through Recruiting Cancer‐Associated Fibroblasts (non-target, keywords=3)
4. Prognostic significance of ANO1 expression in cancers (target, keywords=3)
5. Synthesis and biological evaluation of novel Ani9 derivatives as potent and selective ANO1 inhibitors. (non-target, keywords=1)


## psmb8_thyroid_en

What evidence links PSMB8 to thyroid cancer prognosis or immune response?

### bge_base_control (3.41s)

1. Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (target, keywords=3)
2. Correction: Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (target, keywords=1)
3. Psmb8 inhibits mitochondrial fission and alleviates myocardial ischaemia/reperfusion injury by targeting Drp1 degradation (non-target, keywords=0)
4. HOXD9/miR-451a/PSMB8 axis is implicated in the regulation of cell proliferation and metastasis via PI3K/AKT signaling pathway in human anaplastic thyroid carcinoma (target, keywords=2)
5. Expression of immunoproteasome genes is regulated by cell-intrinsic and –extrinsic factors in human cancers (non-target, keywords=1)

### medcpt (3.11s)

1. Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (target, keywords=3)
2. Correction: Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (target, keywords=1)
3. Increased expression of the immunoproteasome subunits PSMB8 and PSMB9 by cancer cells correlate with better outcomes for triple-negative breast cancers (non-target, keywords=1)
4. HOXD9/miR-451a/PSMB8 axis is implicated in the regulation of cell proliferation and metastasis via PI3K/AKT signaling pathway in human anaplastic thyroid carcinoma (target, keywords=2)
5. Tradeoff between metabolic i-proteasome addiction and immune evasion in triple-negative breast cancer (non-target, keywords=3)

### bge_v2_m3 (9.37s)

1. Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (target, keywords=3)
2. Correction: Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (target, keywords=1)
3. Tradeoff between metabolic i-proteasome addiction and immune evasion in triple-negative breast cancer (non-target, keywords=3)
4. Upregulation of immunoproteasome PSMB8 is associated with Parkinson's disease. (non-target, keywords=1)
5. Sequence Variants in PSMB8/PSMB9 Immunoproteasome Genes and Risk of Urothelial Bladder Carcinoma (non-target, keywords=0)

### qwen3_0_6b (30.59s)

1. Correction: Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (target, keywords=1)
2. Multifaceted investigations of PSMB8 provides insights into prognostic prediction and immunological target in thyroid carcinoma (target, keywords=3)
3. HOXD9/miR-451a/PSMB8 axis is implicated in the regulation of cell proliferation and metastasis via PI3K/AKT signaling pathway in human anaplastic thyroid carcinoma (target, keywords=2)
4. Tradeoff between metabolic i-proteasome addiction and immune evasion in triple-negative breast cancer (non-target, keywords=3)
5. Analysis on methylation and expression of PSMB8 and its correlation with immunity and immunotherapy in lung adenocarcinoma. (non-target, keywords=2)


## hla_drb1_autoimmune_en

What evidence links HLA-DRB1 alleles to autoimmune disease susceptibility?

### bge_base_control (2.96s)

1. Association of HLA-DRB1 Haplotypes With Rheumatoid Arthritis Severity, Mortality, and Treatment Response (target, keywords=3)
2. HLA-DRB1 alleles of susceptibility and protection in Iranians with autoimmune hepatitis. (target, keywords=3)
3. Association of HLA-DRB1 amino acid residues with giant cell arteritis: genetic association study, meta-analysis and geo-epidemiological investigation (target, keywords=4)
4. HLA-DQA1-HLA-DRB1 variants confer susceptibility to pancreatitis induced by thiopurine immunosuppressants (non-target, keywords=2)
5. The Protective Role of HLA-DRB1∗13 in Autoimmune Diseases (target, keywords=2)

### medcpt (3.43s)

1. Current Understanding of an Emerging Role of HLA-DRB1 Gene in Rheumatoid Arthritis–From Research to Clinical Practice (target, keywords=2)
2. Association of HLA-DRB1 Haplotypes With Rheumatoid Arthritis Severity, Mortality, and Treatment Response (target, keywords=3)
3. A molecular basis for the association of the HLA-DRB1 locus, citrullination, and rheumatoid arthritis (target, keywords=0)
4. DNA methylation as a mediator of HLA-DRB1*15:01 and a protective variant in multiple sclerosis (non-target, keywords=2)
5. Comprehensive meta-analysis reveals an association of the HLA-DRB1*1602 allele with autoimmune diseases mediated predominantly by autoantibodies. (target, keywords=2)

### bge_v2_m3 (9.84s)

1. Comprehensive meta-analysis reveals an association of the HLA-DRB1*1602 allele with autoimmune diseases mediated predominantly by autoantibodies. (target, keywords=2)
2. HLA-DRB1 alleles of susceptibility and protection in Iranians with autoimmune hepatitis. (target, keywords=3)
3. Association of HLA-DRB1 Haplotypes With Rheumatoid Arthritis Severity, Mortality, and Treatment Response (target, keywords=3)
4. Association of HLA-DRB1 amino acid residues with giant cell arteritis: genetic association study, meta-analysis and geo-epidemiological investigation (target, keywords=4)
5. HLA-DRB1*04 as a Risk Allele to Systemic Lupus Erythematosus and Lupus Nephritis in the Malay Population of Malaysia (target, keywords=3)

### qwen3_0_6b (34.07s)

1. HLA-DRB1 alleles of susceptibility and protection in Iranians with autoimmune hepatitis. (target, keywords=3)
2. HLA-DRB1*04 as a Risk Allele to Systemic Lupus Erythematosus and Lupus Nephritis in the Malay Population of Malaysia (target, keywords=3)
3. The Protective Role of HLA-DRB1∗13 in Autoimmune Diseases (target, keywords=2)
4. Comprehensive meta-analysis reveals an association of the HLA-DRB1*1602 allele with autoimmune diseases mediated predominantly by autoantibodies. (target, keywords=2)
5. Association of HLA-DRB1 amino acid residues with giant cell arteritis: genetic association study, meta-analysis and geo-epidemiological investigation (target, keywords=4)


## esr1_breast_resistance_ko

ESR1 돌연변이는 유방암에서 타목시펜 또는 내분비 치료 저항성에 어떻게 기여하나요?

### bge_base_control (3.52s)

1. ESR1 mutation as an emerging clinical biomarker in metastatic hormone receptor-positive breast cancer (target, keywords=4)
2. Dihydrotanshinone I targets ESR1 to induce DNA double-strand breaks and proliferation inhibition in hepatocellular carcinoma. (target, keywords=0)
3. ESR1 inhibits ionizing radiation-induced ferroptosis in breast cancer cells via the NEDD4L/CD71 pathway. (target, keywords=0)
4. ESR1 fusions and therapeutic resistance in metastatic breast cancer (target, keywords=3)
5. Randomised, open-label, multicentric phase III trial to evaluate the safety and efficacy of palbociclib in combination with endocrine therapy, guided by ESR1 mutation monitoring in oestrogen receptor-positive, HER2-negative metastatic breast cancer patients: study design of PADA-1 (target, keywords=3)

### medcpt (3.39s)

1. ESR1 activating mutations: From structure to clinical application (target, keywords=2)
2. The Clinical Utility of ESR1 Mutations in Hormone Receptor-Positive, HER2-Negative Advanced Breast Cancer. (target, keywords=3)
3. ESR1 mutation as an emerging clinical biomarker in metastatic hormone receptor-positive breast cancer (target, keywords=4)
4. ESR1 fusions and therapeutic resistance in metastatic breast cancer (target, keywords=3)
5. ESR1 Mutations in Breast Cancer (target, keywords=3)

### bge_v2_m3 (9.85s)

1. ESR1 mutation as an emerging clinical biomarker in metastatic hormone receptor-positive breast cancer (target, keywords=4)
2. ESR1 mutations are frequent in newly diagnosed metastatic and loco-regional recurrence of endocrine-treated breast cancer and carry worse prognosis (target, keywords=4)
3. ESR1 Mutations in Breast Cancer (target, keywords=3)
4. Open-label, phase II, multicenter study of lasofoxifene plus abemaciclib for treating women with metastatic ER+/HER2- breast cancer and an ESR1 mutation after disease progression on prior therapies: ELAINE 2. (target, keywords=3)
5. ESR1 testing on FFPE samples from metastatic lesions in HR + /HER2- breast cancer after progression on CDK4/6 inhibitor therapy (target, keywords=3)

### qwen3_0_6b (37.03s)

1. The Clinical Utility of ESR1 Mutations in Hormone Receptor-Positive, HER2-Negative Advanced Breast Cancer. (target, keywords=3)
2. Imlunestrant a next-generation oral SERD overcomes ESR1 mutant resistance in estrogen receptor–positive breast cancer (target, keywords=3)
3. ESR1 Mutations in Breast Cancer (target, keywords=3)
4. ESR1 mutations are frequent in newly diagnosed metastatic and loco-regional recurrence of endocrine-treated breast cancer and carry worse prognosis (target, keywords=4)
5. ESR1 Y537S and D538G mutations drive resistance to CDK4/6 inhibitors in estrogen receptor-positive breast cancer (target, keywords=2)


## ano1_colorectal_ko

ANO1이 대장암의 진행이나 전이에 관여한다는 근거가 있나요?

### bge_base_control (3.32s)

1. ANO1: central role and clinical significance in non-neoplastic and neoplastic diseases (non-target, keywords=3)
2. Calcium-activated chloride channel ANO1 promotes breast cancer progression by activating EGFR and CAMK signaling (non-target, keywords=1)
3. Prognostic significance of ANO1 expression in cancers (target, keywords=3)
4. High ANO1 expression is a prognostic factor and correlated with an immunosuppressive tumor microenvironment in pancreatic cancer (non-target, keywords=0)
5. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (non-target, keywords=2)

### medcpt (2.57s)

1. Prognostic significance of ANO1 expression in cancers (target, keywords=3)
2. Blockade of calcium-activated chloride channel ANO1 ameliorates ionizing radiation-induced intestinal injury (non-target, keywords=0)
3. ANO1‐Mediated Inhibition of Cancer Ferroptosis Confers Immunotherapeutic Resistance through Recruiting Cancer‐Associated Fibroblasts (non-target, keywords=3)
4. ANO1: central role and clinical significance in non-neoplastic and neoplastic diseases (non-target, keywords=3)
5. ANO1 stabilizes partial EMT to drive colorectal cancer metastasis through PI3K/AKT/mTOR and ERK signaling pathways (target, keywords=4)

### bge_v2_m3 (9.21s)

1. Prognostic significance of ANO1 expression in cancers (target, keywords=3)
2. ANO1: central role and clinical significance in non-neoplastic and neoplastic diseases (non-target, keywords=3)
3. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (non-target, keywords=2)
4. High ANO1 expression is a prognostic factor and correlated with an immunosuppressive tumor microenvironment in pancreatic cancer (non-target, keywords=0)
5. Calcium-activated chloride channel ANO1 promotes breast cancer progression by activating EGFR and CAMK signaling (non-target, keywords=1)

### qwen3_0_6b (23.85s)

1. Calcium-activated chloride channel ANO1 promotes breast cancer progression by activating EGFR and CAMK signaling (non-target, keywords=1)
2. Inhibition of ANO1 by Cis- and Trans-Resveratrol and Their Anticancer Activity in Human Prostate Cancer PC-3 Cells (non-target, keywords=1)
3. ANO1 reprograms cholesterol metabolism and the tumor microenvironment to promote cancer metastasis. (non-target, keywords=2)
4. ANO1 stabilizes partial EMT to drive colorectal cancer metastasis through PI3K/AKT/mTOR and ERK signaling pathways (target, keywords=4)
5. ANO1‐Mediated Inhibition of Cancer Ferroptosis Confers Immunotherapeutic Resistance through Recruiting Cancer‐Associated Fibroblasts (non-target, keywords=3)
