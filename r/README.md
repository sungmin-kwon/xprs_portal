# Legacy RDS input

The current web application renders plots from Python/Parquet data and does not
execute R at request time. Maintainers may place a reviewed legacy source object
at `r/data.RDS` and run `python build_parquet.py` to create the three plotting
tables used by the public breast-cancer profile.

`data.RDS`, `.fam` files, and other source data in this directory are ignored by
Git. They can contain individual-level data and must not be committed.

The original R plotting and rendering helpers were retired after the portal
adopted Plotly and Python-native plot-data generation. Their history remains
available in Git; they are not a supported or reproducible processing pipeline.
