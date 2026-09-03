library(dplyr)
library(data.table)
library(tidyr)

# Function to get attributed values and PRS for all patients
get_all_patients_attributed_values_and_prs <- function(RDS.file, fam_ids) {
  results <- lapply(fam_ids, function(person) {
    # Get the result for each person
    res <- get_person_attributed_value_and_prs(RDS.file, person)
    
    # Add patient ID as a column and keep only the Gene and Attributed_Value_of_Gene
    df <- res$attributed_values
    df$Patient_ID <- person
    return(df)
  })
  
  # Combine all results into one data frame
  all_results <- do.call(rbind, results)
  return(all_results)
}

# Generate the table for all patients
all_patient_results <- get_all_patients_attributed_values_and_prs(data, fam$V1)

# Reshape the data to a wide format and handle duplicates by taking the mean
wide_results <- all_patient_results %>%
  group_by(Gene, Patient_ID) %>%
  summarise(Attributed_Value_of_Gene = mean(Attributed_Value_of_Gene, na.rm = TRUE), .groups = "drop") %>%
  pivot_wider(names_from = Patient_ID, values_from = Attributed_Value_of_Gene)

# Save the wide table to a CSV
write.csv(wide_results, "all_patients_gene_importance.csv", row.names = FALSE)