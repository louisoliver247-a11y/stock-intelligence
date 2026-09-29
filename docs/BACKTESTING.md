# Backtesting — deferred

Milestone 10 will replay the exact live strategy evaluator candle by candle.
Current candle tables include revision availability metadata so future replay can
avoid using later provider corrections as earlier knowledge. The latest-candle
endpoint is not an as-of historical source. Train/validate/test/roll windows,
slippage, fees, ambiguous intrabar stop/target ordering and out-of-sample metrics
must be explicit before presenting any performance statistic.
