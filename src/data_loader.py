import pandas as pd
import json

def load_week1_outputs(data_dir='../data/processed'):
    """
    Load all processed output from Week 1: prices, log returns, point-in-time membership, vn30 index.
    Return to a dictionary for easy unpacking.
    """
    prices_pivot = pd.read_csv(f'{data_dir}/vn30_prices_processed.csv', index_col=0, parse_dates=True)
    log_returns = pd.read_csv(f'{data_dir}/vn30_log_returns_processed.csv', index_col=0, parse_dates=True)
    vn30_index = pd.read_csv(f'{data_dir}/vn30_index_processed.csv', index_col=0, parse_dates=True,).squeeze()

    with open(f'{data_dir}/vn30_membership_point_in_time.json') as f:
        pit_membership_raw = json.load(f)
    pit_membership = {pd.Timestamp(k): v for k, v in pit_membership_raw.items()}

    return {
        'prices_pivot': prices_pivot,
        'log_returns': log_returns,
        'pit_membership': pit_membership,
        'vn30_index': vn30_index
    }