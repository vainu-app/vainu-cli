# Vainu API Client

## Example with API Key:
set vainu API-KE to VAINU_API_KEY environment variable:

Using shell:
```
python3 scripts/vainu_api_client.py --query "?country=FI&business_id=FI01320292" --output "my_companies.json"
```

With code:
```
vainu_api_client = VainuAPIKeyClient()
response = await vainu_api_client.companies(payload="?country=FI&business_id=FI01320292")
print(response)

vainu_api_client = VainuAPIKeyClient()
response = await vainu_api_client.companies_async(payload="?country=FI&business_id=FI01320292")
response.download_to_file("async_response.json")
```

