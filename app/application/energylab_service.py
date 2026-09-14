import json
import urllib.error
import urllib.request


class EnergyLabService:
    def __init__(self, repository):
        self.repository = repository

    def fetch_payload(self, household_id):
        config = self.repository.energylab_integration(household_id)
        if not config.get("enabled"):
            raise ValueError("Die EnergyLab-Verbindung ist nicht aktiviert.")
        request = urllib.request.Request(
            config["base_url"].rstrip("/") + "/api/personallab",
            headers={"Accept": "application/json", "User-Agent": "FinanzLab/1.6.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status != 200:
                    raise ValueError(f"EnergyLab antwortet mit Status {response.status}.")
                return json.loads(response.read(5 * 1024 * 1024))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ValueError(f"EnergyLab ist nicht erreichbar: {getattr(exc, 'reason', exc)}") from exc

    def preview(self, household_id):
        """Fetch EnergyLab and show the complete change set without writing it."""
        return self.repository.preview_energylab_contracts(household_id, self.fetch_payload(household_id))

    def sync(self, household_id):
        try:
            payload = self.fetch_payload(household_id)
            result = self.repository.sync_energylab_contracts(household_id, payload)
            message = (
                f"{result['contracts']} Verträge geprüft: {result['created']} neu, "
                f"{result['updated']} aktualisiert, {result.get('unchanged', 0)} unverändert"
                f" und {result.get('deactivated', 0)} beendet."
            )
            if result.get("unmatched_accounts"):
                message += f" {len(result['unmatched_accounts'])} Kontoname(n) wurden in FinanzLab nicht gefunden; dafür wird das Standardkonto verwendet."
            self.repository.record_energylab_sync(household_id, "ok", message)
            return {**result, "message": message}
        except Exception as exc:
            self.repository.record_energylab_sync(household_id, "error", str(exc))
            raise

    def sync_all(self):
        results = []
        for config in self.repository.enabled_energylab_integrations():
            try:
                results.append({"household_id": config["household_id"], "result": self.sync(config["household_id"])})
            except Exception as exc:
                results.append({"household_id": config["household_id"], "error": str(exc)})
        return results
