/** @odoo-module **/
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const TITLES = {
    home: "Tyre Alignment",
    begin: "Begin Alignment",
    spec: "Primary Specifications",
    wheels: "Four Wheel Alignment",
};

export class AlignmentApp extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.titles = TITLES;
        this.panelRef = useRef("axlePanel");
        this.panelRef = useRef("axlePanel");
        this.state = useState({
            screen: "home",
            vehicles: [],
            specs: [],
            vehicleId: false,
            specId: false,
            jobId: false,
            jobName: "",
            specTable: null,
            wheels: null,
            selected: null,
            axleInfo: null,
            loadingAxle: false,
        });
        onWillStart(async () => {
            const context = (this.props.action && this.props.action.context) || {};
            if (context.alignment_job_id) {
                await this.openJob(context.alignment_job_id);
            }
        });
    }

    // ---------- helpers ----------
    deg(value) {
        return `${Number(value || 0).toFixed(2)}°`;
    }

    summaryText() {
        const summary = this.state.wheels && this.state.wheels.summary;
        if (summary === "ok") {
            return "Within spec";
        }
        if (summary === "out") {
            return "Adjust red values";
        }
        return "No specification";
    }

    openList(model, name) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            views: [[false, "list"], [false, "kanban"], [false, "form"]],
            target: "current",
        });
    }

    openRecord(model, id) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ---------- screen 1 -> 2 ----------
    goHome() {
        this.state.screen = "home";
    }

    async goBegin() {
        const [vehicles, specs] = await Promise.all([
            this.orm.searchRead("fleet.vehicle", [], ["display_name"]),
            this.orm.searchRead("tyre.alignment.spec", [], ["name", "wheel_size"]),
        ]);
        this.state.vehicles = vehicles;
        this.state.specs = specs;
        if (!this.state.vehicleId && vehicles.length) {
            this.state.vehicleId = vehicles[0].id;
        }
        if (!this.state.specId && specs.length) {
            this.state.specId = specs[0].id;
        }
        this.state.screen = "begin";
    }

    onVehicleChange(ev) {
        this.state.vehicleId = parseInt(ev.target.value, 10) || false;
    }

    onSpecChange(ev) {
        this.state.specId = parseInt(ev.target.value, 10) || false;
    }

    // ---------- screen 2: new / continue ----------
    async start(mode) {
        if (!this.state.vehicleId) {
            this.notification.add("Choose a vehicle first. Add one from the Vehicles tile.", { type: "warning" });
            return;
        }
        const jobId = await this.orm.call(
            "tyre.alignment.job", "start_alignment",
            [this.state.vehicleId, this.state.specId || false, mode]
        );
        await this.openJob(jobId);
    }

    async openJob(jobId) {
        const [job] = await this.orm.read("tyre.alignment.job", [jobId], ["name", "vehicle_id", "spec_id"]);
        this.state.jobId = jobId;
        this.state.jobName = job.name;
        this.state.vehicleId = job.vehicle_id && job.vehicle_id[0];
        this.state.specId = job.spec_id && job.spec_id[0];
        this.state.selected = null;
        this.state.axleInfo = null;
        if (this.state.specId) {
            this.state.specTable = await this.orm.call("tyre.alignment.job", "get_spec_table", [[jobId]]);
            this.state.screen = "spec";
        } else {
            this.state.specTable = null;
            await this.showWheels();
        }
    }

    // ---------- screen 4 ----------
    async showWheels() {
        this.state.wheels = await this.orm.call("tyre.alignment.job", "get_wheel_view", [[this.state.jobId]]);
        this.state.screen = "wheels";
    }

    // Tyre touch -> both tyres on that axle with their readings
    async onWheelClick(position) {
        this.state.selected = position;
        this.scrollToPanel();
        this.scrollToPanel();
        const axle = position.startsWith("F") ? "front" : "rear";
        if (this.state.axleInfo && this.state.axleInfo.axle === axle) {
            return;
        }
        this.state.loadingAxle = true;
        try {
            this.state.axleInfo = await this.orm.call(
                "tyre.alignment.job", "get_axle_info", [[this.state.jobId], axle]
            );
        } finally {
            this.state.loadingAxle = false;
        }
    }

    // Phones: bring the axle panel into view after a tyre tap
    scrollToPanel() {
        if (window.innerWidth > 700) {
            return;
        }
        setTimeout(() => {
            const el = this.panelRef.el;
            if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "nearest" });
            }
        }, 80);
    }

    // Phones: bring the axle panel into view after a tyre tap
    scrollToPanel() {
        if (window.innerWidth > 700) {
            return;
        }
        setTimeout(() => {
            const el = this.panelRef.el;
            if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "nearest" });
            }
        }, 80);
    }

    // ---------- bottom bar ----------
    async back() {
        const screen = this.state.screen;
        if (screen === "wheels" && this.state.specTable) {
            this.state.screen = "spec";
        } else if (screen === "wheels" || screen === "spec") {
            await this.goBegin();
        } else {
            this.goHome();
        }
    }

    async next() {
        if (this.state.screen === "spec") {
            await this.showWheels();
        } else if (this.state.screen === "wheels") {
            await this.orm.call("tyre.alignment.job", "action_done", [[this.state.jobId]]);
            this.notification.add(`${this.state.jobName} saved as done.`, { type: "success" });
            this.state.jobId = false;
            this.state.wheels = null;
            this.goHome();
        }
    }
}

AlignmentApp.template = "tyre_tracking.AlignmentApp";
registry.category("actions").add("tyre_tracking_alignment", AlignmentApp);
