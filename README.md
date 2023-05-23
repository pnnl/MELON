Clone Repository and Submodule:

```git clone -b [branch] https://stash.pnnl.gov/scm/melon/melon.git [your_folder_name]```

```cd [your_folder_name]```

```git submodule update --init --recursive```

Directories in **bold**

Script names are only placeholders meant to provide a rough sketch of workflow

MELON
- **input_data**
    - CBSA
    - RBSA
    - TELL
    - other external datasets
- **src**
    - *standardize_input.py*
        - CBSA/RBSA &rarr; UrbanBEM standardized input
        - Handles scenarios (i.e. with/without EV)
    - *add_ev.py*
        - Adds electric vehicle ElectricEquipment objects to UrbanBEM IDFs
    - *postprocess.py*
        - aggregates UrbanBEM demand, adds to demand from other sectors, and calculates gap
    - *run.sbatch*
        1. runs *standardize_input.py*
        2. creates IDFs with UrbanBEM
        3. runs *add_ev.py* if requested
        4. runs simulations in parallel on UrbanBEM
        5. runs *postprocess.py*
- **b2g**
    - *run.json*
    - *building.json*
    - *secondary_feeder.json*
    - *supply_side.json*
    - *building.py*
    - *secondary_feeder.py*
    - *supply_side.py*
    - Secondary feeder GRIDLAB-D files (modified)
- **output** (not in repo - built during run)
- **calibration** (not in repo - built during run)


