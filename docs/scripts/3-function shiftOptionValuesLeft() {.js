function shiftOptionValuesLeft() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const data = sheet.getDataRange().getValues();

  const header = data[0];
  const optName1Idx = header.indexOf("Option1 Name");
  const optValue1Idx = header.indexOf("Option1 Value");
  const optName2Idx = header.indexOf("Option2 Name");
  const optValue2Idx = header.indexOf("Option2 Value");
  const optName3Idx = header.indexOf("Option3 Name");
  const optValue3Idx = header.indexOf("Option3 Value");

  for (let i = 1; i < data.length; i++) {
    let row = data[i];

    // Case: Option1 is empty, Option2 has values → shift to Option1
    if (!row[optName1Idx] && !row[optValue1Idx] && row[optName2Idx] && row[optValue2Idx]) {
      sheet.getRange(i + 1, optName1Idx + 1).setValue(row[optName2Idx]);
      sheet.getRange(i + 1, optValue1Idx + 1).setValue(row[optValue2Idx]);
      sheet.getRange(i + 1, optName2Idx + 1).setValue("");
      sheet.getRange(i + 1, optValue2Idx + 1).setValue("");
    }

    // Refresh the row after possible shift
    row = sheet.getRange(i + 1, 1, 1, header.length).getValues()[0];

    // Case: Option2 is empty, Option3 has values → shift to Option2
    if (!row[optName2Idx] && !row[optValue2Idx] && row[optName3Idx] && row[optValue3Idx]) {
      sheet.getRange(i + 1, optName2Idx + 1).setValue(row[optName3Idx]);
      sheet.getRange(i + 1, optValue2Idx + 1).setValue(row[optValue3Idx]);
      sheet.getRange(i + 1, optName3Idx + 1).setValue("");
      sheet.getRange(i + 1, optValue3Idx + 1).setValue("");
    }
  }
}
