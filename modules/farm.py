import copy
import random
from datetime import date

class Batch:
    def __init__(self, batch_id, species, quantity, stage, start_date, bs_cycle_days=28, mf_cycle_days=30, fs_cycle_days=90, bs_mortality_std=0.05, mf_mortality_std=0.1, fs_mortality_std=0.05):
        self.batch_id = batch_id
        self.species = species
        self.quantity = quantity
        self.stage = stage
        self.start_date = start_date
        self.bs_cycle_days = bs_cycle_days
        self.mf_cycle_days = mf_cycle_days
        self.fs_cycle_days = fs_cycle_days
        self.bs_mortality_std = bs_mortality_std
        self.mf_mortality_std = mf_mortality_std
        self.fs_mortality_std = fs_mortality_std

        # Set the end date depending on the stage
        if stage == "BS":
            self.end_date = start_date + bs_cycle_days
        elif stage == "MF":
            self.end_date = start_date + mf_cycle_days
        elif stage == "FS":
            self.end_date = start_date + fs_cycle_days
        else:
            self.end_date = None

    def is_ready_to_transition(self, day):
        if self.end_date is None:
            return False
        return day >= self.end_date

    def change_stage(self, day):
        if self.stage == "BS":
            self.stage = "MF"
            self.end_date = day + self.mf_cycle_days
        elif self.stage == "MF":
            self.stage = "FS"
            self.end_date = day + self.fs_cycle_days
        elif self.stage == "FS":
            self.stage = "OP"
            self.end_date = None

        self.start_date = day

    def simulate_mortality(self):
        # Mortality logic to be implemented as needed
        pass


class Farm:
    def __init__(self, inventory, tank_capacity, tank_num, stage_capacities, production_order):
        self.inventory = inventory
        self.capacity = tank_capacity * tank_num
        self.stage_capacities = stage_capacities
        self.production_order = production_order
        self.species_set = {batch.species for batch in inventory}

    def check_capacity(self, stage_capacities, batch=None):
        if batch is None:
            return stage_capacities["BS"] > 0
        elif batch.stage == "BS":
            return stage_capacities["MF"] >= batch.quantity
        elif batch.stage == "MF":
            return stage_capacities["FS"] >= batch.quantity
        elif batch.stage == "FS":
            return stage_capacities["OP"] >= batch.quantity
        return False

    def create_batch(self, day, species, quantity_ceiling):
        batch_id = f"TEST-{random.randint(1, 10000)}"
        batch_quantity = min(quantity_ceiling, 100)
        return Batch(batch_id=batch_id, species=species, quantity=batch_quantity, stage="BS", start_date=day)

    def choose_species(self, species_shortfall):
        max_shortfall_share = -1
        max_species = None
        for species, shortfall in species_shortfall.items():
            shortfall_share = shortfall / self.production_order[species]
            if shortfall_share > max_shortfall_share:
                max_shortfall_share = shortfall_share
                max_species = species

        return max_species or random.choice(list(self.species_set))

    def forecast(self, days, production_order, desired_output):
        rolling_inventory = []
        rolling_totals = []
        rolling_changes = []
        rolling_capacity = []
        totals_zero = {"BS": 0, "MF": 0, "FS": 0, "OP": 0, "SF": 0}
        totals_zero_species = {spec: totals_zero.copy() for spec in self.species_set}

        for day in range(days):
            cur_totals = copy.deepcopy(totals_zero)
            cur_totals_species = copy.deepcopy(totals_zero_species)
            forecast_changes = copy.deepcopy(totals_zero)
            forecast_changes_species = copy.deepcopy(totals_zero_species)
            stage_capacity_remaining = self.stage_capacities.copy()

            for batch in self.inventory:
                if batch.is_ready_to_transition(day) and self.check_capacity(stage_capacity_remaining, batch):
                    batch.change_stage(day)
                    stage_capacity_remaining[batch.stage] -= batch.quantity
                    forecast_changes[batch.stage] += batch.quantity
                    forecast_changes_species[batch.species][batch.stage] += batch.quantity

                cur_totals[batch.stage] += batch.quantity
                cur_totals_species[batch.species][batch.stage] += batch.quantity

            cur_totals["SF"] = desired_output - cur_totals["OP"]
            for species in self.species_set:
                if species in production_order:
                    cur_totals_species[species]["SF"] = production_order[species] - cur_totals_species[species]["OP"]

            cur_avail_capacity = self.capacity - cur_totals["BS"] - cur_totals["MF"] - cur_totals["FS"]

            rolling_inventory.append(cur_totals)
            rolling_totals.append({"overall": cur_totals, "species": cur_totals_species})
            rolling_changes.append({"overall": forecast_changes, "species": forecast_changes_species})
            rolling_capacity.append({"overall": cur_avail_capacity, "stage": stage_capacity_remaining})

        return rolling_inventory, rolling_totals, rolling_changes, rolling_capacity

    def plan_future(self, days, species_shortfall, forecasted_capacity):
        hypothetical_inventory = []
        hypothetical_rolling_inventory = []
        hypothetical_rolling_changes = []
        hypothetical_rolling_totals = []
        hypothetical_rolling_capacity = []
        shortfall = sum(species_shortfall.values())

        for day in range(days):
            stage_capacity_remaining = forecasted_capacity[day]["stage"]
            farm_capacity_remaining = forecasted_capacity[day]["overall"]

            while shortfall > 0 and stage_capacity_remaining["BS"] > 0 and farm_capacity_remaining > 0:
                quantity_ceiling = min(shortfall, stage_capacity_remaining["BS"], farm_capacity_remaining)
                new_species = self.choose_species(species_shortfall)
                new_batch = self.create_batch(day, new_species, quantity_ceiling)
                hypothetical_inventory.append(new_batch)

                stage_capacity_remaining["BS"] -= new_batch.quantity
                farm_capacity_remaining -= new_batch.quantity
                shortfall -= new_batch.quantity
                species_shortfall[new_batch.species] -= new_batch.quantity

        return hypothetical_inventory, hypothetical_rolling_totals, hypothetical_rolling_changes, hypothetical_rolling_capacity