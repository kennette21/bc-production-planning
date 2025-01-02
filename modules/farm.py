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
            cur_inventory = {}  # Track batch-specific details
            cur_totals = copy.deepcopy(totals_zero)
            cur_totals_species = copy.deepcopy(totals_zero_species)
            forecast_changes = copy.deepcopy(totals_zero)
            forecast_changes_species = copy.deepcopy(totals_zero_species)
            stage_capacity_remaining = self.stage_capacities.copy()

            # Simulate transitions for each batch
            for batch in self.inventory:
                is_ready = batch.is_ready_to_transition(day)
                stage_capacity_exists = self.check_capacity(stage_capacity_remaining, batch)

                if is_ready and stage_capacity_exists:
                    batch.change_stage(day)
                    stage_capacity_remaining[batch.stage] -= batch.quantity
                    forecast_changes[batch.stage] += batch.quantity
                    forecast_changes_species[batch.species][batch.stage] += batch.quantity

                # Simulate mortality
                batch.simulate_mortality()

                # Update current inventory and totals
                cur_inventory[batch.batch_id] = {
                    "species": batch.species,
                    "stage": batch.stage,
                    "quantity": batch.quantity,
                }
                cur_totals[batch.stage] += batch.quantity
                cur_totals_species[batch.species][batch.stage] += batch.quantity

            # Calculate shortfall and available capacity
            cur_totals["SF"] = desired_output - cur_totals["OP"]
            for species in self.species_set:
                if species in production_order:
                    cur_totals_species[species]["SF"] = (
                        production_order[species] - cur_totals_species[species]["OP"]
                    )

            cur_avail_capacity = (
                self.capacity - cur_totals["BS"] - cur_totals["MF"] - cur_totals["FS"]
            )

            # Add current totals to rolling lists
            rolling_inventory.append(cur_inventory)
            rolling_totals.append({"overall": cur_totals, "species": cur_totals_species})
            rolling_changes.append({"overall": forecast_changes, "species": forecast_changes_species})
            rolling_capacity.append({"overall": cur_avail_capacity, "stage": stage_capacity_remaining})

            # Debugging Logs (optional)
            print(f"Day: {day}")
            print("Current Totals:", cur_totals)
            print("Current Totals by Species:", cur_totals_species)
            print("Overall Capacity Remaining:", cur_avail_capacity)
            print("Stage Capacity Remaining:", stage_capacity_remaining)
            print("")

        return rolling_inventory, rolling_totals, rolling_changes, rolling_capacity

    def plan_future(self, days, species_shortfall, forecasted_capacity):
        hypothetical_inventory = []
        hypothetical_rolling_inventory = []
        hypothetical_rolling_changes = []
        hypothetical_rolling_totals = []
        hypothetical_rolling_capacity = []
        shortfall = sum(species_shortfall.values())

        for day in range(days):
            cur_inventory = {}

            # Calculate the capacity remaining for the day
            if day == 0:
                farm_capacity_remaining = forecasted_capacity[0]["overall"]
            else:
                farm_capacity_remaining = (
                    forecasted_capacity[day]["overall"]
                    - hypothetical_totals["BS"]
                    - hypothetical_totals["MF"]
                    - hypothetical_totals["FS"]
                )

            # Initialize blank values for the day
            blank_totals = {"BS": 0, "MF": 0, "FS": 0, "OP": 0}
            hypothetical_changes = blank_totals.copy()
            hypothetical_changes_species = {
                spec: blank_totals.copy() for spec in self.species_set
            }
            hypothetical_totals = blank_totals.copy()
            hypothetical_totals_species = {
                spec: blank_totals.copy() for spec in self.species_set
            }
            stage_capacity_remaining = forecasted_capacity[day]["stage"]

            # Try to add batches today if there is a shortfall and capacity
            while (
                shortfall > 0
                and stage_capacity_remaining["BS"] > 0
                and farm_capacity_remaining > 0
            ):
                # Decide the quantity and species
                quantity_ceiling = min(
                    shortfall, stage_capacity_remaining["BS"], farm_capacity_remaining
                )
                new_species = self.choose_species(species_shortfall)

                # Create new batch
                new_batch = self.create_batch(day, new_species, quantity_ceiling)
                hypothetical_inventory.append(new_batch)

                # Reduce capacity and shortfall
                stage_capacity_remaining["BS"] -= new_batch.quantity
                farm_capacity_remaining -= new_batch.quantity
                shortfall -= new_batch.quantity
                species_shortfall[new_batch.species] -= new_batch.quantity

                # Add to Additions
                hypothetical_changes[new_batch.stage] += new_batch.quantity
                hypothetical_changes_species[new_batch.species][
                    new_batch.stage
                ] += new_batch.quantity

            # Simulate quantity and transition to the next day for each batch
            for batch in hypothetical_inventory:
                is_ready = batch.is_ready_to_transition(day)
                stage_capacity_exists = self.check_capacity(stage_capacity_remaining, batch)

                # Transition batch if ready and capacity exists
                if is_ready and stage_capacity_exists:
                    batch.change_stage(day)

                    stage_capacity_remaining[batch.stage] -= batch.quantity
                    hypothetical_changes[batch.stage] += batch.quantity
                    hypothetical_changes_species[batch.species][batch.stage] += batch.quantity

                batch.simulate_mortality()

                cur_inventory[batch.batch_id] = {
                    "stage": batch.stage,
                    "quantity": batch.quantity,
                }

                # Generate daily total
                hypothetical_totals[batch.stage] += batch.quantity
                hypothetical_totals_species[batch.species][batch.stage] += batch.quantity

            # Save the daily inventory, totals, changes, and capacity
            hypothetical_rolling_inventory.append(cur_inventory)
            hypothetical_rolling_totals.append(
                {"overall": hypothetical_totals, "species": hypothetical_totals_species}
            )
            hypothetical_rolling_capacity.append(
                {"overall": farm_capacity_remaining, "stage": stage_capacity_remaining}
            )
            hypothetical_rolling_changes.append(
                {"overall": hypothetical_changes, "species": hypothetical_changes_species}
            )

        return (
            hypothetical_rolling_inventory,
            hypothetical_rolling_totals,
            hypothetical_rolling_changes,
            hypothetical_rolling_capacity,
        )