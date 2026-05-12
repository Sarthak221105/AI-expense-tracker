// utils.js — pure JS helpers only (no JSX here)
export const fmt = new Intl.NumberFormat('en-IN', {
  style: 'currency', currency: 'INR', maximumFractionDigits: 0,
});
export const fmtNum = (n) => fmt.format(n ?? 0);

export const MONTHS      = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
export const MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December'];

export const CAT_COLORS = {
  'Food & Dining':      '#ff6b6b',
  'Groceries':          '#ffa94d',
  'Transport':          '#74c0fc',
  'Shopping':           '#f783ac',
  'Entertainment':      '#da77f2',
  'Health & Fitness':   '#63e6be',
  'Utilities':          '#a9e34b',
  'Finance & Insurance':'#4dabf7',
  'Education':          '#69db7c',
  'Salary':             '#51cf66',
  'Business Income':    '#2f9e44',
  'ATM Withdrawal':     '#868e96',
  'Bank Transfer':      '#495057',
  'EMI & Loans':        '#ff8787',
  'Subscriptions':      '#cc5de8',
  'Rent':               '#e64980',
  'Travel & Holidays':  '#20c997',
  'Other':              '#adb5bd',
};

export const USER_KEY = 'finance_user_id';
