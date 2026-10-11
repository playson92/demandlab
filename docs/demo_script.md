# Three-minute recruiter walkthrough

1. **Product and forecast (45 seconds).** Use the regular product shortcut, then
   search by name or SKU. Explain recorded sales, the forecast issue date and the
   visible knowledge boundary. The default is the validation-selected weekday
   mean, with one uncertainty band. Compare methods, then switch the band method.
   Show the full range; large sales spikes are real records and remain accessible.
2. **Inventory scenarios (75 seconds).** Open the inventory shortcut with the
   selected product and method. Explain hypothetical costs, the lost-sales model
   and the two sales paths. Save scenario A as the reference, change delivery time
   from 7 to 14 days, then inspect B and the differences. Initial stock stays fixed
   when delivery time changes. Read the changed parameters and export CSV/JSON.
   This is a scenario comparison, not an optimization or a business savings claim.
3. **Methods and results (60 seconds).** Select validation, then final test.
   Explain MAE in units, WAPE as error (lower is better), percentage bias,
   interval coverage and width. Separate global and selected-product results.
   The validation-selected method remains the default even though the tree's
   final WAPE is lower. Inspect horizon errors, difficult products and provenance.

All views read the same frozen 80-product study. The forecast date is
10 November 2011 and the final horizon ends on 8 December 2011. Observed sales
are not the complete unconstrained demand. Historical test labels have already
been disclosed; frontend review cannot create a new independent test.
