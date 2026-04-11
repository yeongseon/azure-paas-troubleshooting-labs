---
hide:
  - toc
validation:
  az_cli:
    last_tested: null
    result: not_tested
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Ingress Host Header and SNI Behavior

!!! info "Status: Planned"

## 1. Question

How does Azure Container Apps ingress handle Server Name Indication (SNI) and host header routing, and what happens with mismatched or missing headers in custom domain scenarios?

## 2. Why this matters

Container Apps uses an Envoy-based ingress layer that routes traffic based on host headers and SNI. When customers configure custom domains, mismatches between the SNI value (TLS layer) and the host header (HTTP layer) can cause unexpected routing — traffic may reach the wrong app, receive a default certificate error, or fail silently. These edge cases are difficult to debug without understanding the ingress routing logic.

## 3. Customer symptom

"Custom domain works intermittently" or "Getting responses from the wrong app when using my custom domain."

## 4. Hypothesis

Ingress routing decisions in Azure Container Apps depend on both TLS SNI and HTTP host header context. Missing or mismatched values will produce deterministic routing or certificate outcomes that explain wrong-app responses and TLS/domain errors in custom domain scenarios.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure Container Apps |
| SKU / Plan | Consumption environment |
| Region | Korea Central |
| Runtime | Containerized HTTP app (nginx + test API) |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Config

**Controlled:**

- Number of Container Apps in the environment
- Custom domain and certificate configuration
- SNI value in TLS ClientHello
- Host header value in HTTP request

**Observed:**

- Which app receives the request
- Certificate presented during TLS handshake
- HTTP response status and body
- Ingress access logs

## 7. Instrumentation

- `curl` and `openssl s_client` with explicit SNI and host-header permutations
- Container app access logs and revision-level request logs
- Azure Monitor logs for ingress and environment diagnostics
- DNS query tools (`nslookup`, `dig`) to confirm resolution path during each case
- Test endpoint responses that include app identity for unambiguous routing verification

## 8. Procedure

### 8.1 Infrastructure setup

Create the lab environment and two apps in `koreacentral`.

```bash
RG="rg-ingress-sni-lab"
LOCATION="koreacentral"
ENV_NAME="cae-ingress-sni-lab"
ACR_NAME="acringresssni$RANDOM"
ALPHA_APP_NAME="app-alpha"
BETA_APP_NAME="app-beta"

az group create --name "$RG" --location "$LOCATION"

az acr create \
  --resource-group "$RG" \
  --name "$ACR_NAME" \
  --sku Basic \
  --location "$LOCATION" \
  --admin-enabled true

az containerapp env create \
  --resource-group "$RG" \
  --name "$ENV_NAME" \
  --location "$LOCATION"
```

For custom-domain testing, add hostnames with managed certificates (requires a real DNS-managed domain).

```bash
az containerapp hostname add \
  --resource-group "$RG" \
  --name "$ALPHA_APP_NAME" \
  --hostname "alpha.example.com" \
  --environment "$ENV_NAME" \
  --certificate-type Managed
```

If real domain validation is not available, proceed with self-signed certificates and test routing using `curl --resolve ... --cacert ...`. A fallback method is to use default app FQDNs and validate SNI behavior with `openssl s_client` while overriding host headers at HTTP layer.

### 8.2 Application code

Prepare two minimal nginx apps that each return their own identity.

`nginx-alpha.conf`:

```nginx
server {
    listen 8080;
    location / {
        return 200 "app-alpha\n";
    }
}
```

`nginx-beta.conf`:

```nginx
server {
    listen 8080;
    location / {
        return 200 "app-beta\n";
    }
}
```

Build two images that embed each config (for example, from `nginx:alpine` with config copied into `/etc/nginx/conf.d/default.conf`).

### 8.3 Deploy

Build and push images to ACR, then deploy both Container Apps with ingress on port `8080`.

```bash
ACR_LOGIN_SERVER=$(az acr show --resource-group "$RG" --name "$ACR_NAME" --query loginServer --output tsv)
ACR_USERNAME=$(az acr credential show --name "$ACR_NAME" --query username --output tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" --output tsv)

az acr build --registry "$ACR_NAME" --image alpha:1.0.0 --file Dockerfile.alpha .
az acr build --registry "$ACR_NAME" --image beta:1.0.0 --file Dockerfile.beta .

az containerapp create \
  --resource-group "$RG" \
  --environment "$ENV_NAME" \
  --name "$ALPHA_APP_NAME" \
  --image "$ACR_LOGIN_SERVER/alpha:1.0.0" \
  --target-port 8080 \
  --ingress external \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD"

az containerapp create \
  --resource-group "$RG" \
  --environment "$ENV_NAME" \
  --name "$BETA_APP_NAME" \
  --image "$ACR_LOGIN_SERVER/beta:1.0.0" \
  --target-port 8080 \
  --ingress external \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD"
```

### 8.4 Test execution

Build a deterministic matrix for SNI and host header combinations. For each case, capture full command, certificate output, response body, and status code.

1. Correct SNI + correct Host.
2. Correct SNI + wrong Host.
3. Wrong SNI + correct Host.
4. No SNI + correct Host.
5. Correct SNI + no Host.

```bash
ALPHA_FQDN=$(az containerapp show --resource-group "$RG" --name "$ALPHA_APP_NAME" --query properties.configuration.ingress.fqdn --output tsv)
INGRESS_IP=$(nslookup "$ALPHA_FQDN" | awk '/^Address: / { print $2 }' | tail -n 1)
```

Examples (replace domains/FQDNs to match your setup):

```bash
# 1) Correct SNI + correct Host
curl --verbose --resolve "alpha.example.com:443:$INGRESS_IP" "https://alpha.example.com/"

# 2) Correct SNI + wrong Host
curl --verbose --resolve "alpha.example.com:443:$INGRESS_IP" --header "Host: beta.example.com" "https://alpha.example.com/"

# 3) Wrong SNI + correct Host
curl --verbose --resolve "wrong.example.com:443:$INGRESS_IP" --header "Host: alpha.example.com" "https://wrong.example.com/"

# 4) No SNI + correct Host (openssl without -servername)
printf "GET / HTTP/1.1\r\nHost: alpha.example.com\r\nConnection: close\r\n\r\n" | openssl s_client -connect "$INGRESS_IP:443"

# 5) Correct SNI + no Host
printf "GET / HTTP/1.1\r\nConnection: close\r\n\r\n" | openssl s_client -connect "$INGRESS_IP:443" -servername "alpha.example.com"
```

If using self-signed certificates, add `--cacert /path/to/ca.crt` to `curl` commands.

### 8.5 Data collection

For each matrix row, record the following fields in an evidence table:

- `test_case_id`
- `sni_value`
- `host_header_value`
- `certificate_cn_san`
- `http_status_code`
- `response_body_identity` (`app-alpha`, `app-beta`, or error)
- `tls_or_http_error_message`

Collect Container Apps logs around each request timestamp.

```bash
az containerapp logs show \
  --resource-group "$RG" \
  --name "$ALPHA_APP_NAME" \
  --type system \
  --follow false

az containerapp logs show \
  --resource-group "$RG" \
  --name "$BETA_APP_NAME" \
  --type system \
  --follow false
```

When custom domains are configured, compare expected certificate CN/SAN with observed handshake output and verify whether backend identity matches intended routing.

### 8.6 Cleanup

Delete all resources after collecting artifacts.

```bash
az group delete --name "$RG" --yes --no-wait
```

## 9. Expected signal

- Matching SNI and host header routes traffic predictably to the intended app with expected certificate.
- Missing or mismatched SNI produces certificate mismatches or default ingress certificate behavior.
- Mismatched host header can route to an unexpected backend or return domain-not-configured style errors.
- The observed outcome category is repeatable for each SNI/host-header combination.

## 10. Results

_Awaiting execution._

## 11. Interpretation

_Awaiting execution._

## 12. What this proves

_Awaiting execution._

## 13. What this does NOT prove

_Awaiting execution._

## 14. Support takeaway

_Awaiting execution._

## 15. Reproduction notes

- Use unique response payload markers per app so routing destination is obvious in every test.
- Flush local DNS cache when switching between FQDN and direct test variants.
- Capture full TLS handshake output alongside HTTP response for each case.
- Keep one certificate and domain change at a time to avoid overlapping configuration effects.

## 16. Related guide / official docs

- [Microsoft Learn: Custom domains in Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-managed-certificates)
- [azure-container-apps-practical-guide](https://github.com/yeongseon/azure-container-apps-practical-guide)
