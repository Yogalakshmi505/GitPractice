/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class TyreDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = useState({
            vehicles: [],
            vehicleId: false,
            tyres: {},          // { FL: {id, serial, condition}, ... }
            selected: null,     // touched position
            axle: null,         // 'front' / 'rear'
            axleTyres: [],      // every tyre on the touched axle
            loading: false,
        });
        onWillStart(async () => {
            this.state.vehicles = await this.orm.searchRead("fleet.vehicle", [], ["name", "license_plate"]);
            if (this.state.vehicles.length) {
                await this.loadVehicle(this.state.vehicles[0].id);
            }
        });
    }

    async loadVehicle(vehicleId) {
        this.state.vehicleId = vehicleId;
        this.state.selected = null;
        this.state.axle = null;
        this.state.axleTyres = [];
        this.state.tyres = await this.orm.call("tyre.master", "get_vehicle_tyres", [vehicleId]);
    }

    async onVehicleChange(ev) {
        const vehicleId = parseInt(ev.target.value, 10);
        if (vehicleId) {
            await this.loadVehicle(vehicleId);
        }
    }

    // Tyre touch -> fetch every tyre on that axle
    async onTyreTouch(position) {
        this.state.selected = position;
        const axle = position.startsWith("F") ? "front" : "rear";
        if (axle === this.state.axle) {
            return;
        }
        this.state.loading = true;
        try {
            this.state.axleTyres = await this.orm.call(
                "tyre.master", "get_axle_details", [this.state.vehicleId, axle]
            );
            this.state.axle = axle;
        } finally {
            this.state.loading = false;
        }
    }

    tyreClass(position) {
        const tyre = this.state.tyres[position];
        const condition = tyre ? `tyre-${tyre.condition}` : "tyre-empty";
        const active = this.state.selected === position ? "active" : "";
        return `tyre-item ${condition} ${active}`;
    }

    openTyre(tyreId) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "tyre.master",
            res_id: tyreId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

TyreDashboard.template = "tyre_tracking.Dashboard";
registry.category("actions").add("tyre_tracking_dashboard", TyreDashboard);
