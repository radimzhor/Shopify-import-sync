function copyCustomFieldsToCorrectOptions() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const data = sheet.getDataRange().getValues();

  const header = data[0];

  // Ordered custom fields (columns to check left to right)
  const customFields = [
    "Barva (product.metafields.custom.barva)",
    "Velikost (product.metafields.custom.velikost)",
    "Provedení (product.metafields.custom.provedeni)",
    "Hodnota (product.metafields.custom.hodnota)",
    "Pevnost (product.metafields.custom.pevnost)",
    "Značka (product.metafields.custom.znacka)",
    "Šířka (product.metafields.custom.sirka)",
    "Velikost balení (product.metafields.custom.velikost_baleni)"
  ];

  // Get index of custom fields
  const customFieldIndexes = customFields.map(name => header.indexOf(name));

  // Get indexes for Option columns
  const option1ValueIndex = header.indexOf("Option1 Value");
  const option2ValueIndex = header.indexOf("Option2 Value");
  const option3ValueIndex = header.indexOf("Option3 Value");

  for (let i = 1; i < data.length; i++) {
    let valuesToCopy = [];

    // Collect first 3 non-empty custom field values in order
    for (let j = 0; j < customFieldIndexes.length; j++) {
      const value = data[i][customFieldIndexes[j]];
      if (value !== "" && value !== null) {
        valuesToCopy.push(value);
        if (valuesToCopy.length === 3) break; // stop once we have 3
      }
    }

    // Apply values to Option columns
    if (valuesToCopy[0]) {
      sheet.getRange(i + 1, option1ValueIndex + 1).setValue(valuesToCopy[0]);
    }
    if (valuesToCopy[1]) {
      sheet.getRange(i + 1, option2ValueIndex + 1).setValue(valuesToCopy[1]);
    }
    if (valuesToCopy[2]) {
      sheet.getRange(i + 1, option3ValueIndex + 1).setValue(valuesToCopy[2]);
    }
  }
}
