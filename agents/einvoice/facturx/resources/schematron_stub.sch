<?xml version="1.0" encoding="UTF-8"?>
<!-- TEMP_VALIDATOR: Placeholder Schematron for Factur-X Comfort (A2). -->
<sch:schema xmlns:sch="http://purl.oclc.org/dsdl/schematron">
  <sch:pattern id="totals-consistency">
    <sch:rule context="FacturX/Totals">
      <sch:assert test="NetAmount + TaxAmount = GrossAmount">
        NetAmount plus TaxAmount muss GrossAmount ergeben (TEMP_VALIDATOR).
      </sch:assert>
    </sch:rule>
  </sch:pattern>
</sch:schema>

