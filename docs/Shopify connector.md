# Shopify Import & Sync  
  
Shopify Import & Sync je rozšíření v Mergado Store. Rozšíření integruje data eshopu v Mergadu s eshopem na Shopify. Rozšíření je vázané na eshop v Mergadu a má přístup ke všem projektům eshopu v Mergadu. Každý projekt obsahuje jeden produktový feed, připravený ve formátu Shopify CSV používaný pro import uploadem do Shopify. Rozšíření umožňuje ze zvoleného projektu v eshopu vytáhnout výstupní url přes API, z url si stáhnout CSV a data rozparsovat a nahrát přes API do Shopify, tedy importovat produkty. Dále u nahraných produktů vytáhne nové Shopify ID a zapíše ho přes API zpět do  projektu k produktům do elementu shopify_id který nejdříve vyyvoří (přes API). Dále umožní nastavit pravidelnou synchronizaci počet ks skladem z Mergado projektu do Shopify, případně dalších elementů (cena,..). V první verzi umožní nahrát produkty z jednoho projektu do Shopify, v dalších verzích pak bude možné přidat další zdroj - jiný projekt v mergadu, např projekt s produkty od jiného dodavatele. Obecná logika celého postupu je, že klient nahraje produktový feed(y) do Mergada, kde si data připraví pro import do Shopify ve formátu Shopify CSV. využije filtry a pravidla pro optimalizaci a přípravu dat, skryje produkty co nahrát nechce. Následně vytvoří spojení se svým Shopify Storem v rozšíření Mergado Keychain. A pomocí rozšíření Shopify Import & Sync naimportuje upravené produkty do Shopify přes API. Shopify Import & Sync následně umožní pravidlný sync stock produktů. Důležitý je progress bar při nahrávání produktů do Shopify, a log kolik se nahrálo, kolik se nenahrálo a proč, možnost stažení reportu v csv, log se ukládá a uživatel se k němu mlže vrátit. Log pak obsahuje i informace o další akcích jako je jednotlivé sync stock produktů,   
Propojení s Shopify storem - bude přes Keychain Proxy, dokumentace viz https://mergado.docs.apiary.io/#reference/shopify/shopify-api-proxy/  
Bude to rozšíření bázané na eshop  
Sync produktů v projektu vs v Shopify   
- porovnání kolik je matched/unmatched  
- podle čeho?   
    - handle? handle+title? nespolehlivé  
    - Variant SKU vs SKU nejjistější  
    - Variant Barcode vs Barcode  
- import a zápis Shopify ID z Shopify zpět do feedu  
    - vytvořit nový skrytý element shopify_id  
    - importovat shopify id přes api a zapsat do shopify_id elementu  
Sync STOCK_AMOUNT - je to stock varianty!  
- api call na hodnotu elementu, a sync do shopify  
- řeší se změna available, ne on_hand ( "name": "available“ v rámci Variables)  
- scopes  
    - write_inventory  
    - read_inventory  
    - read_locations?  
    - Shopify navíc vyžaduje, aby uživatel/token měl i oprávnění „update inventory“ na úrovni uživatele.  
Sync ceny  
