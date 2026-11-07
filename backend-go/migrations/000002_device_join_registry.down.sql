-- Migration 000002 Down: Revert Device Registry, Generations, Join Counters & Join Transactions

DROP TABLE IF EXISTS join_transactions CASCADE;
DROP TABLE IF EXISTS device_join_counters CASCADE;
DROP TABLE IF EXISTS device_generations CASCADE;
DROP TABLE IF EXISTS devices CASCADE;
