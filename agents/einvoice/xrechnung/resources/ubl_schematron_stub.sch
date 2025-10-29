<?xml version="1.0" encoding="UTF-8"?>
<!-- TEMP_VALIDATOR: Placeholder Schematron enforcing totals consistency. -->
<sch:schema xmlns:sch="http://purl.oclc.org/dsdl/schematron">
  <sch:pattern id="legal-totals">
    <sch:rule context="Invoice">
      <sch:assert test="decimal(LegalMonetaryTotal/TaxInclusiveAmount) = decimal(LegalMonetaryTotal/TaxExclusiveAmount) + decimal(TaxTotal/TaxAmount)">
        TaxInclusiveAmount muss TaxExclusiveAmount plus TaxAmount entsprechen (TEMP_VALIDATOR).
      </sch:assert>
    </sch:rule>
  </sch:pattern>
</sch:schema>

