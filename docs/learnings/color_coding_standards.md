# Color Coding Standards for Financial Data

## Overview
This document defines the color coding standards for displaying financial data in tables and UI components.

## Rules

### 1. Price Information (NO Color Coding)
**All price information should be displayed WITHOUT color coding**, using only the negative sign (-) for negative values.

**Examples:**
- Entry Price: `$100.00` or `-$5.50`
- Current Price: `$105.00` or `-$2.00`
- Net Cost: `$10.00` or `-$0.50`
- Strike Price: `$100.00`
- Call Premium: `$5.00`
- Put Premium: `$3.50`

**Where Applied:**
- RR Details page: Entry Price, Net Cost in history table
- RR List page: Entry Price, Current Price
- Stock Detail page: Risk Reversal Net Cost ($) and Net Cost (%)
- All option prices (strike, bid, ask, last price)
- All stock prices (current, SMA 50, SMA 200)

### 2. Change/Return Information (Color Coding REQUIRED)
**All change and return information MUST be color coded** to indicate performance:
- **Green (text-success)**: Positive values (good performance)
- **Red (text-danger)**: Negative values (bad performance)
- **No color**: Zero values

**Examples:**
- Change: `$5.00` (green) or `-$2.00` (red)
- Change %: `5.00%` (green) or `-2.00%` (red)
- Total Return: `$10.00` (green) or `-$5.00` (red)
- Return %: `10.00%` (green) or `-5.00%` (red)

**Where Applied:**
- RR List page: Change and Change % columns
- Covered Calls table: Total Return Exercised ($ and %), Total Return Not Exercised ($ and %)
- Any other performance/change metrics

## Implementation Pattern

### Price Information (No Color)
```jinja2
<td>${{ "%.2f"|format(price) }}</td>
```

### Change/Return Information (With Color)
```jinja2
<td>
    {% if change > 0 %}
        <span class="text-success">${{ "%.2f"|format(change) }}</span>
    {% elif change < 0 %}
        <span class="text-danger">${{ "%.2f"|format(change) }}</span>
    {% else %}
        ${{ "%.2f"|format(change) }}
    {% endif %}
</td>
```

## Rationale

1. **Price Information**: Prices are absolute values. A negative price (credit) or positive price (debit) doesn't inherently mean "good" or "bad" - it depends on the context and strategy. Therefore, no color coding is needed.

2. **Change/Return Information**: Changes and returns indicate performance relative to a baseline. Positive changes/returns are generally good (green), negative are bad (red). Color coding helps users quickly identify performance.

## Checklist for New Features

When adding new tables or columns:

1. **Identify the data type:**
   - Is it a price/absolute value? → NO color coding
   - Is it a change/return/performance metric? → YES color coding

2. **Verify consistency:**
   - Check existing similar columns for consistency
   - Follow the patterns established in this document

3. **Test:**
   - Verify negative values show with minus sign
   - Verify color coding works for positive/negative/zero values
   - Verify no color coding on price columns

## Examples of Correct Implementation

### ✅ Correct: Price (No Color)
```jinja2
<td>${{ "%.2f"|format(entry.entry_price) }}</td>
<td>${{ "%.2f"|format(row.net_cost) }}</td>
```

### ✅ Correct: Change (With Color)
```jinja2
<td>
    {% if entry.change > 0 %}
        <span class="text-success">${{ "%.2f"|format(entry.change) }}</span>
    {% elif entry.change < 0 %}
        <span class="text-danger">${{ "%.2f"|format(entry.change) }}</span>
    {% else %}
        ${{ "%.2f"|format(entry.change) }}
    {% endif %}
</td>
```

### ❌ Incorrect: Price with Color
```jinja2
{% if price < 0 %}
    <span class="text-success">${{ "%.2f"|format(price) }}</span>
{% else %}
    <span class="text-danger">${{ "%.2f"|format(price) }}</span>
{% endif %}
```

### ❌ Incorrect: Change without Color
```jinja2
<td>${{ "%.2f"|format(change) }}</td>
```

## Last Updated
2026-01-13
