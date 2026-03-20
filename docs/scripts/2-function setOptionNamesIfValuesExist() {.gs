function setOptionNamesIfValuesExist() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const data = sheet.getDataRange().getValues();

  const header = data[0];

  // Ordered list of custom columns to check
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

  // Get the indexes of those custom fields
  const customFieldIndexes = customFields.map(name => header.indexOf(name));

  // Option name column indexes
  const option1NameIndex = header.indexOf("Option1 Name");
  const option2NameIndex = header.indexOf("Option2 Name");
  const option3NameIndex = header.indexOf("Option3 Name");

  // Loop through rows
  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    let optionNames = [];

    for (let j = 0; j < customFieldIndexes.length; j++) {
      const colIndex = customFieldIndexes[j];
      const value = row[colIndex];
      if (value !== "" && value !== null) {
        // Get first word from the column name
        const label = customFields[j].split(" ")[0];
        optionNames.push(label);
        if (optionNames.length === 3) break;
      }
    }

    if (optionNames[0]) {
      sheet.getRange(i + 1, option1NameIndex + 1).setValue(optionNames[0]);
    }
    if (optionNames[1]) {
      sheet.getRange(i + 1, option2NameIndex + 1).setValue(optionNames[1]);
    }
    if (optionNames[2]) {
      sheet.getRange(i + 1, option3NameIndex + 1).setValue(optionNames[2]);
    }
  }
}
