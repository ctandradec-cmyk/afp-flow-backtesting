# AFP Flow Backtesting

This repository contains the Python implementation of the backtesting
methodology developed to evaluate potential flow estimates of Chilean
pension funds (AFPs) in local equities.

## Objective

The objective of the backtesting framework is to assess the historical
performance of a proxy based on portfolio-weight deviations between
individual pension fund administrators and the AFP system.

## Methodology

For each security and AFP, the methodology compares the portfolio weight
of the individual administrator with a historical system-level reference.

The reference is constructed using a six-month historical window.

The resulting signal is evaluated against subsequently observed portfolio
movements.

## Performance Metrics

The backtesting considers metrics such as:

- Mean Absolute Error (MAE)
- Relative MAE
- Directional accuracy
- Error relative to the portfolio position

## Repository Structure

`backtesting_afp.py`

Main Python implementation of the backtesting methodology.

## Data Availability

The original datasets used in the analysis are not included in this
repository due to confidentiality restrictions.

The repository therefore contains the computational methodology but not
the proprietary input data.

## Academic Context

This code was developed as part of an academic internship project in 2026.
