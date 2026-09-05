import json
import urllib.error
import urllib.request


class EnergyLabService:
    def __init__(self, repository):
        self.repository = repository

    def sync(self, household_id):
        config = self.repository.energylab_integration(household_id)
        if not config.get("enabled"):
            raise ValueError("Die EnergyLab-Verbindung ist nicht aktiviert.")
        request = urllib.request.Request(
            config["base_url"].rstrip("/") + "/api/personallab",
            headers={"Accept": "application/json", "User-Agent": "FinanzLab/1.0.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status != 200:
                    raise ValueError(f"EnergyLab antwortet mit Status {response.status}.")
                payload = json.loads(response.read(5 * 1024 * 1024))
            result = self.repository.sync_energylab_contracts(household_id, payload)
            message = f"{result['contracts']} Verträge geprüft, {result['created']} neu, {result['updated']} aktualisiert."
            if result.get("unmatched_accounts"):
                message += f" {len(result['unmatched_accounts'])} Kontoname(n) wurden in FinanzLab nicht gefunden; dafür wird das Standardkonto verwendet."
            self.repository.record_energylab_sync(household_id, "ok", message)
            return {**result, "message": message}
        except (urllib.error.URLError, TimeoutError) as exc:
            message = f"EnergyLab ist nicht erreichbar: {getattr(exc, 'reason', exc)}"
            self.repository.record_energylab_sync(household_id, "error", message)
            raise ValueError(message) from exc
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
