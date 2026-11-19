# -*- coding: utf-8 -*-
"""
Tests for the tyre_tracking module (Odoo 16).

Covers: tyre.master, tyre.fitment, tyre.alignment.spec / spec.line / job /
reading, the alignment screen helper methods and the access rights.

TC numbers match the Excel sheet "Tyre_Tracking_Unit_Test_Cases.xlsx".
TC-90 to TC-104 are browser (UI) tests and are done by hand, not here.

Run:
    odoo-bin -d <test_db> -i tyre_tracking --test-tags /tyre_tracking --stop-after-init
"""
import itertools

from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

POSITIONS = ['FL', 'FR', 'RL', 'RR']
DB_ERRORS = (IntegrityError, ValidationError)


@tagged('post_install', '-at_install', 'tyre_tracking')
class TestTyreTracking(TransactionCase):

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Tyre = cls.env['tyre.master']
        cls.Fitment = cls.env['tyre.fitment']
        cls.Spec = cls.env['tyre.alignment.spec']
        cls.SpecLine = cls.env['tyre.alignment.spec.line']
        cls.Job = cls.env['tyre.alignment.job']
        cls.Reading = cls.env['tyre.alignment.reading']
        cls._serial = itertools.count(1)

        # fleet.vehicle needs a model, and the model needs a brand.
        cls.brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Test Brand'})
        cls.vmodel = cls.env['fleet.vehicle.model'].create({
            'name': 'Test Model', 'brand_id': cls.brand.id})
        cls.vehicle = cls._make_vehicle('TN30AB1234')
        cls.vehicle2 = cls._make_vehicle('TN30CD5678')

        # Demo specification loaded from data/alignment_spec_data.xml
        cls.spec = cls.env.ref('tyre_tracking.spec_toyota_avensis')

    @classmethod
    def _make_vehicle(cls, plate):
        return cls.env['fleet.vehicle'].create({
            'model_id': cls.vmodel.id, 'license_plate': plate})

    def _tyre(self, **vals):
        vals.setdefault('name', 'SN-%04d' % next(self._serial))
        return self.Tyre.create(vals)

    def _fit(self, tyre, position, vehicle=None, **extra):
        vals = {'tyre_id': tyre.id,
                'vehicle_id': (vehicle or self.vehicle).id,
                'position': position}
        vals.update(extra)
        return self.Fitment.create(vals)

    def _fit_all(self, vehicle=None):
        """Fit four new tyres on FL, FR, RL, RR and return them by position."""
        tyres = {}
        for pos in POSITIONS:
            tyres[pos] = self._tyre(brand='MRF', wear_level=30)
            self._fit(tyres[pos], pos, vehicle)
        return tyres

    def _job(self, spec=True, vehicle=None, **extra):
        vals = {'vehicle_id': (vehicle or self.vehicle).id,
                'spec_id': self.spec.id if spec else False}
        vals.update(extra)
        return self.Job.create(vals)

    def _reading(self, job, position, parameter):
        return job.reading_ids.filtered(
            lambda r: r.position == position and r.parameter == parameter)

    def _set_reading(self, job, position, parameter, value):
        reading = self._reading(job, position, parameter)
        reading.write({'value': value})
        return reading

    def _set_all_in_spec(self, job):
        """Put all 10 readings inside the Avensis specification."""
        for pos in ('FL', 'FR'):
            self._set_reading(job, pos, 'camber', -0.17)
            self._set_reading(job, pos, 'caster', 6.00)
            self._set_reading(job, pos, 'toe', 0.09)
        for pos in ('RL', 'RR'):
            self._set_reading(job, pos, 'camber', -1.00)
            self._set_reading(job, pos, 'toe', 0.05)

    def _spec_line(self, axle, parameter, spec=None):
        return (spec or self.spec).line_ids.filtered(
            lambda l: l.axle == axle and l.parameter == parameter)

    def _assert_db_error(self, model, vals):
        """`create(vals)` must fail on a database / validation error."""
        with mute_logger('odoo.sql_db'):
            with self.assertRaises(Exception):
                model.create(vals)

    # ==================================================================
    # A. Tyre master - fields and computed values
    # ==================================================================
    def test_tyre_default_values(self):
        """TC-01: a new tyre is in stock, 'good', with no vehicle/position."""
        tyre = self._tyre()
        self.assertEqual(tyre.state, 'stock')
        self.assertEqual(tyre.condition, 'good')
        self.assertFalse(tyre.axle)
        self.assertFalse(tyre.vehicle_id)
        self.assertFalse(tyre.position)

    def test_tyre_serial_is_mandatory(self):
        """TC-02: Serial No (name) is required."""
        count = self.Tyre.search_count([])
        self._assert_db_error(self.Tyre, {'brand': 'MRF'})
        self.assertEqual(self.Tyre.search_count([]), count)

    def test_axle_front_positions(self):
        """TC-03: FL and FR belong to the front axle."""
        for pos in ('FL', 'FR'):
            with self.subTest(position=pos):
                self.assertEqual(self._tyre(position=pos).axle, 'front')

    def test_axle_rear_positions(self):
        """TC-04: RL and RR belong to the rear axle."""
        for pos in ('RL', 'RR'):
            with self.subTest(position=pos):
                self.assertEqual(self._tyre(position=pos).axle, 'rear')

    def test_axle_cleared_when_position_cleared(self):
        """TC-05: removing the position clears the axle."""
        tyre = self._tyre(position='FL')
        self.assertEqual(tyre.axle, 'front')
        tyre.write({'position': False})
        self.assertFalse(tyre.axle)

    def test_condition_good_below_60(self):
        """TC-06: wear below 60 % is 'good'."""
        for wear in (0, 30, 59.99):
            with self.subTest(wear=wear):
                self.assertEqual(self._tyre(wear_level=wear).condition, 'good')

    def test_condition_warning_60_to_79(self):
        """TC-07: 60 is the first 'warning' value."""
        for wear in (60, 70, 79.99):
            with self.subTest(wear=wear):
                self.assertEqual(self._tyre(wear_level=wear).condition, 'warning')

    def test_condition_replace_from_80(self):
        """TC-08: 80 is the first 'replace' value."""
        for wear in (80, 95, 100):
            with self.subTest(wear=wear):
                self.assertEqual(self._tyre(wear_level=wear).condition, 'replace')

    def test_condition_recomputed_when_wear_changes(self):
        """TC-09: good -> warning -> replace -> good as wear changes."""
        tyre = self._tyre(wear_level=10)
        for wear, expected in ((10, 'good'), (65, 'warning'),
                               (85, 'replace'), (20, 'good')):
            tyre.write({'wear_level': wear})
            self.assertEqual(tyre.condition, expected)

    def test_known_issue_wear_outside_0_100_is_accepted(self):
        """TC-10 (KNOWN ISSUE D-1): wear -5 and 150 are saved without error.

        Fix: add a constraint wear_level between 0 and 100.
        When fixed, change this test to assert ValidationError.
        """
        low = self._tyre(wear_level=-5)
        high = self._tyre(wear_level=150)
        self.assertEqual(low.condition, 'good')
        self.assertEqual(high.condition, 'replace')

    # ==================================================================
    # B. Tyre master - constraints and scrap
    # ==================================================================
    def test_one_tyre_per_position_on_a_vehicle(self):
        """TC-11: the same vehicle cannot have two tyres at the same position."""
        self._fit(self._tyre(), 'FL')
        with mute_logger('odoo.sql_db'):
            with self.assertRaises(IntegrityError) as cm:
                self._tyre(vehicle_id=self.vehicle.id, position='FL')
        self.assertIn('vehicle_position_uniq', str(cm.exception))

    def test_same_position_on_different_vehicles(self):
        """TC-12: the unique rule is per vehicle."""
        a = self._tyre(vehicle_id=self.vehicle.id, position='FL')
        b = self._tyre(vehicle_id=self.vehicle2.id, position='FL')
        self.assertTrue(a and b)

    def test_several_stock_tyres_without_vehicle(self):
        """TC-13: empty vehicle/position do not clash (NULL values)."""
        tyres = self._tyre() | self._tyre()
        self.assertEqual(len(tyres), 2)
        self.assertEqual(set(tyres.mapped('state')), {'stock'})

    def test_scrap_fitted_tyre(self):
        """TC-14: scrap removes the tyre from the vehicle."""
        tyre = self._tyre()
        self._fit(tyre, 'FR')
        self.assertEqual(tyre.state, 'active')

        tyre.action_scrap()

        self.assertEqual(tyre.state, 'scrap')
        self.assertFalse(tyre.vehicle_id)
        self.assertFalse(tyre.position)
        self.assertFalse(tyre.axle)

    def test_scrap_frees_the_position(self):
        """TC-15: a new tyre can use the position of a scrapped tyre."""
        old = self._tyre()
        self._fit(old, 'FL')
        old.action_scrap()
        new = self._tyre()
        self._fit(new, 'FL')
        self.assertEqual(new.state, 'active')
        self.assertEqual(new.position, 'FL')

    def test_scrap_several_tyres(self):
        """TC-16: scrap works on a recordset."""
        a, b = self._tyre(), self._tyre()
        self._fit(a, 'FL')
        self._fit(b, 'FR')
        (a | b).action_scrap()
        self.assertEqual(set((a | b).mapped('state')), {'scrap'})
        self.assertFalse((a | b).mapped('vehicle_id'))

    def test_scrap_already_scrapped_tyre(self):
        """TC-17: scrapping twice is harmless."""
        tyre = self._tyre()
        tyre.action_scrap()
        tyre.action_scrap()
        self.assertEqual(tyre.state, 'scrap')
        self.assertFalse(tyre.vehicle_id)

    def test_known_issue_direct_write_does_not_fit_the_tyre(self):
        """TC-18 (KNOWN ISSUE D-2): vehicle/position written directly.

        The tyre keeps state 'stock', no fitment record is created and
        get_vehicle_tyres() does not return it. Fix: set state = active,
        or block the direct write and force the Fitment screen.
        """
        tyre = self._tyre()
        tyre.write({'vehicle_id': self.vehicle.id, 'position': 'RL'})
        self.assertEqual(tyre.state, 'stock')
        self.assertFalse(tyre.fitment_ids)
        self.assertEqual(self.Tyre.get_vehicle_tyres(self.vehicle.id), {})

    # ==================================================================
    # C. Tyre master - methods used by the dashboard JS
    # ==================================================================
    def test_get_vehicle_tyres(self):
        """TC-19: all fitted tyres are returned, keyed by position."""
        tyres = self._fit_all()
        result = self.Tyre.get_vehicle_tyres(self.vehicle.id)
        self.assertEqual(set(result), set(POSITIONS))
        for pos in POSITIONS:
            self.assertEqual(result[pos]['id'], tyres[pos].id)
            self.assertEqual(result[pos]['serial'], tyres[pos].name)
            self.assertEqual(result[pos]['condition'], 'good')

    def test_get_vehicle_tyres_vehicle_without_tyres(self):
        """TC-20: a vehicle with no tyre gives an empty dict."""
        self.assertEqual(self.Tyre.get_vehicle_tyres(self.vehicle2.id), {})

    def test_get_vehicle_tyres_ignores_scrapped_tyre(self):
        """TC-21: a scrapped tyre is not returned."""
        tyres = self._fit_all()
        tyres['FR'].action_scrap()
        result = self.Tyre.get_vehicle_tyres(self.vehicle.id)
        self.assertEqual(set(result), {'FL', 'RL', 'RR'})

    def test_get_vehicle_tyres_isolates_vehicles(self):
        """TC-22: only the tyres of the asked vehicle are returned."""
        self._fit_all(self.vehicle)
        other = self._tyre()
        self._fit(other, 'FL', self.vehicle2)
        result = self.Tyre.get_vehicle_tyres(self.vehicle2.id)
        self.assertEqual(list(result), ['FL'])
        self.assertEqual(result['FL']['id'], other.id)

    def test_get_axle_details_front(self):
        """TC-23: front axle returns FL then FR."""
        self._fit_all()
        details = self.Tyre.get_axle_details(self.vehicle.id, 'front')
        self.assertEqual([d['position'] for d in details], ['FL', 'FR'])

    def test_get_axle_details_rear(self):
        """TC-24: rear axle returns RL then RR."""
        self._fit_all()
        details = self.Tyre.get_axle_details(self.vehicle.id, 'rear')
        self.assertEqual([d['position'] for d in details], ['RL', 'RR'])

    def test_get_axle_details_with_missing_tyre(self):
        """TC-25: only the fitted tyre is returned."""
        self._fit(self._tyre(), 'FL')
        details = self.Tyre.get_axle_details(self.vehicle.id, 'front')
        self.assertEqual([d['position'] for d in details], ['FL'])

    def test_get_axle_details_invalid_axle(self):
        """TC-26: an unknown axle gives an empty list, no error."""
        self._fit_all()
        self.assertEqual(self.Tyre.get_axle_details(self.vehicle.id, 'side'), [])

    def test_tyre_info_content(self):
        """TC-27: _tyre_info() keys and blank brand/size handling."""
        tyre = self._tyre(speed=80, temperature=45, odometer=1200, wear_level=30)
        self._fit(tyre, 'FL')
        info = tyre._tyre_info()
        self.assertEqual(set(info), {
            'id', 'position', 'position_label', 'serial', 'brand', 'size',
            'speed', 'temperature', 'odometer', 'wear', 'condition'})
        self.assertEqual(info['id'], tyre.id)
        self.assertEqual(info['position_label'], 'Front Left')
        self.assertEqual(info['serial'], tyre.name)
        self.assertEqual(info['brand'], '')
        self.assertEqual(info['size'], '')
        self.assertEqual(info['wear'], 30)
        self.assertEqual(info['condition'], 'good')

    def test_tyre_info_needs_single_record(self):
        """TC-28: _tyre_info() uses ensure_one()."""
        with self.assertRaises(ValueError):
            (self._tyre() | self._tyre())._tyre_info()

    # ==================================================================
    # D. Fitment
    # ==================================================================
    def test_fit_a_stock_tyre(self):
        """TC-29: fitting makes the tyre active on the vehicle position."""
        tyre = self._tyre()
        self._fit(tyre, 'FL')
        self.assertEqual(tyre.state, 'active')
        self.assertEqual(tyre.vehicle_id, self.vehicle)
        self.assertEqual(tyre.position, 'FL')

    def test_fitment_replaces_old_tyre(self):
        """TC-30: the old tyre goes back to stock; no unique error."""
        old, new = self._tyre(), self._tyre()
        self._fit(old, 'FL')
        self._fit(new, 'FL')
        self.assertEqual(old.state, 'stock')
        self.assertFalse(old.vehicle_id)
        self.assertFalse(old.position)
        self.assertEqual(new.state, 'active')
        self.assertEqual(new.position, 'FL')

    def test_refit_same_tyre_same_position(self):
        """TC-31: re-fitting the same tyre does not remove it."""
        tyre = self._tyre()
        self._fit(tyre, 'FL')
        self._fit(tyre, 'FL')
        self.assertEqual(tyre.state, 'active')
        self.assertEqual(tyre.position, 'FL')
        self.assertEqual(self.Tyre.search_count([
            ('vehicle_id', '=', self.vehicle.id), ('position', '=', 'FL')]), 1)

    def test_move_tyre_to_another_position(self):
        """TC-32: moving FL -> FR leaves FL empty."""
        tyre = self._tyre()
        self._fit(tyre, 'FL')
        self._fit(tyre, 'FR')
        self.assertEqual(tyre.position, 'FR')
        self.assertEqual(self.Tyre.get_vehicle_tyres(self.vehicle.id).keys(), {'FR'})

    def test_move_tyre_to_another_vehicle(self):
        """TC-33: moving to vehicle B frees the position on vehicle A."""
        tyre = self._tyre()
        self._fit(tyre, 'FL', self.vehicle)
        self._fit(tyre, 'FL', self.vehicle2)
        self.assertEqual(tyre.vehicle_id, self.vehicle2)
        self.assertEqual(self.Tyre.get_vehicle_tyres(self.vehicle.id), {})

    def test_fit_four_tyres_in_one_create(self):
        """TC-34: create() with a list of 4 fitments."""
        tyres = [self._tyre() for _ in POSITIONS]
        fits = self.Fitment.create([
            {'tyre_id': t.id, 'vehicle_id': self.vehicle.id, 'position': pos}
            for t, pos in zip(tyres, POSITIONS)])
        self.assertEqual(len(fits), 4)
        for tyre, pos in zip(tyres, POSITIONS):
            self.assertEqual(tyre.state, 'active')
            self.assertEqual(tyre.position, pos)

    def test_fitment_mandatory_fields(self):
        """TC-35: tyre, vehicle and position are all required."""
        tyre = self._tyre()
        base = {'tyre_id': tyre.id, 'vehicle_id': self.vehicle.id, 'position': 'FL'}
        for missing in ('tyre_id', 'vehicle_id', 'position'):
            with self.subTest(missing=missing):
                vals = {k: v for k, v in base.items() if k != missing}
                self._assert_db_error(self.Fitment, vals)

    def test_fitment_default_date(self):
        """TC-36: fitment_date defaults to today."""
        fit = self._fit(self._tyre(), 'FL')
        self.assertEqual(fit.fitment_date, fields.Date.context_today(fit))

    def test_fitment_history_on_tyre(self):
        """TC-37: history lines are shown newest first."""
        tyre = self._tyre()
        self._fit(tyre, 'FL', fitment_date='2026-01-01')
        self._fit(tyre, 'FR', fitment_date='2026-02-01')
        tyre.invalidate_recordset(['fitment_ids'])
        self.assertEqual(tyre.fitment_ids.mapped('position'), ['FR', 'FL'])

    def test_known_issue_fitting_a_scrapped_tyre(self):
        """TC-38 (KNOWN ISSUE D-3): a scrapped tyre can be fitted again.

        Fix: raise UserError in tyre.fitment.create when tyre state is scrap.
        When fixed, change this test to assert UserError.
        """
        tyre = self._tyre()
        tyre.action_scrap()
        self._fit(tyre, 'FL')
        self.assertEqual(tyre.state, 'active')

    def test_known_issue_odometer_at_fit_not_copied(self):
        """TC-39 (KNOWN ISSUE D-4): tyre.odometer is not updated by fitment.

        Confirm with the business whether it should be.
        """
        tyre = self._tyre(odometer=0)
        self._fit(tyre, 'FL', odometer_at_fit=5000)
        self.assertEqual(tyre.odometer, 0)

    def test_known_issue_delete_fitment_does_not_unfit(self):
        """TC-40 (KNOWN ISSUE D-5): deleting the fitment leaves the tyre fitted."""
        tyre = self._tyre()
        fit = self._fit(tyre, 'FL')
        fit.unlink()
        self.assertEqual(tyre.state, 'active')
        self.assertEqual(tyre.position, 'FL')

    # ==================================================================
    # E. Alignment specification
    # ==================================================================
    def test_demo_spec_is_loaded(self):
        """TC-41: Avensis spec with 9 lines (5 front, 4 rear)."""
        self.assertEqual(self.spec.name, 'TOYOTA AVENSIS 2015-2016')
        self.assertEqual(self.spec.wheel_size, '17"')
        self.assertEqual(len(self.spec.line_ids), 9)
        front = self.spec.line_ids.filtered(lambda l: l.axle == 'front')
        rear = self.spec.line_ids.filtered(lambda l: l.axle == 'rear')
        self.assertEqual(set(front.mapped('parameter')),
                         {'caster', 'camber', 'sai', 'ind_toe', 'total_toe'})
        self.assertEqual(set(rear.mapped('parameter')),
                         {'camber', 'ind_toe', 'total_toe', 'thrust'})

    def test_demo_spec_values(self):
        """TC-42: front caster values; SAI and thrust have no range."""
        caster = self._spec_line('front', 'caster')
        self.assertAlmostEqual(caster.min_val, 5.25)
        self.assertAlmostEqual(caster.pref_val, 6.00)
        self.assertAlmostEqual(caster.max_val, 6.75)
        self.assertAlmostEqual(caster.cross_val, 0.75)
        self.assertFalse(self._spec_line('front', 'sai').has_range)
        self.assertFalse(self._spec_line('rear', 'thrust').has_range)

    def test_check_inside_range(self):
        """TC-43: a value inside min-max is 'ok'."""
        line = self._spec_line('front', 'camber')       # -0.92 .. 0.58
        self.assertEqual(line._check(0.0), 'ok')

    def test_check_range_boundaries(self):
        """TC-44: min and max are included; just outside is 'out'."""
        line = self._spec_line('front', 'camber')
        self.assertEqual(line._check(line.min_val), 'ok')
        self.assertEqual(line._check(line.max_val), 'ok')
        self.assertEqual(line._check(line.min_val - 0.01), 'out')
        self.assertEqual(line._check(line.max_val + 0.01), 'out')

    def test_check_line_without_range(self):
        """TC-45: has_range = False always gives 'none'."""
        self.assertEqual(self._spec_line('front', 'sai')._check(99), 'none')

    def test_check_empty_line(self):
        """TC-46: an empty recordset gives 'none', no error."""
        self.assertEqual(self.SpecLine.browse()._check(1.0), 'none')

    def test_delete_spec_deletes_lines(self):
        """TC-47: spec lines are removed with their spec (cascade)."""
        spec = self.Spec.create({'name': 'Cascade spec', 'line_ids': [
            Command.create({'axle': 'front', 'parameter': 'camber'}),
            Command.create({'axle': 'front', 'parameter': 'caster'}),
            Command.create({'axle': 'rear', 'parameter': 'camber'})]})
        lines = spec.line_ids
        self.assertEqual(len(lines), 3)
        spec.unlink()
        self.assertFalse(lines.exists())

    def test_spec_line_mandatory_fields(self):
        """TC-48: spec, parameter and axle are required."""
        spec = self.Spec.create({'name': 'Mandatory spec'})
        base = {'spec_id': spec.id, 'parameter': 'camber', 'axle': 'front'}
        for missing in ('spec_id', 'parameter', 'axle'):
            with self.subTest(missing=missing):
                vals = dict(base)
                vals[missing] = False
                self._assert_db_error(self.SpecLine, vals)

    # ==================================================================
    # F. Alignment job
    # ==================================================================
    def test_create_job(self):
        """TC-49: job gets name ALN/<id>, state measuring and a date."""
        job = self._job()
        self.assertEqual(job.name, 'ALN/%05d' % job.id)
        self.assertEqual(job.state, 'measuring')
        self.assertTrue(job.date)

    def test_job_creates_10_readings(self):
        """TC-50: 3 readings per front wheel, 2 per rear wheel, all 0."""
        job = self._job()
        pairs = {(r.position, r.parameter) for r in job.reading_ids}
        expected = {(p, prm) for p in ('FL', 'FR')
                    for prm in ('camber', 'caster', 'toe')}
        expected |= {(p, prm) for p in ('RL', 'RR') for prm in ('camber', 'toe')}
        self.assertEqual(len(job.reading_ids), 10)
        self.assertEqual(pairs, expected)
        self.assertEqual(set(job.reading_ids.mapped('value')), {0.0})

    def test_job_vehicle_is_mandatory(self):
        """TC-51: a job without a vehicle cannot be saved."""
        self._assert_db_error(self.Job, {'spec_id': self.spec.id})

    def test_create_two_jobs_in_one_call(self):
        """TC-52: each job has its own name and its own 10 readings."""
        jobs = self.Job.create([
            {'vehicle_id': self.vehicle.id}, {'vehicle_id': self.vehicle2.id}])
        self.assertEqual(len(set(jobs.mapped('name'))), 2)
        for job in jobs:
            self.assertEqual(len(job.reading_ids), 10)

    def test_ensure_readings_does_not_duplicate(self):
        """TC-53: calling _ensure_readings() again adds nothing."""
        job = self._job()
        job._ensure_readings()
        job._ensure_readings()
        self.assertEqual(len(job.reading_ids), 10)

    def test_ensure_readings_restores_deleted_reading(self):
        """TC-54: a deleted reading is created again."""
        job = self._job()
        self._reading(job, 'FL', 'camber').unlink()
        self.assertEqual(len(job.reading_ids), 9)
        job._ensure_readings()
        self.assertEqual(len(job.reading_ids), 10)
        self.assertTrue(self._reading(job, 'FL', 'camber'))

    def test_job_without_spec(self):
        """TC-55: readings exist and every status is 'none'."""
        job = self._job(spec=False)
        self.assertEqual(len(job.reading_ids), 10)
        self.assertEqual(set(job.reading_ids.mapped('status')), {'none'})

    def test_delete_job_deletes_readings(self):
        """TC-56: readings are removed with the job (cascade)."""
        job = self._job()
        readings = job.reading_ids
        job.unlink()
        self.assertFalse(readings.exists())

    # ==================================================================
    # G. Reading status
    # ==================================================================
    def test_readings_within_spec(self):
        """TC-57: front-left readings inside the Avensis ranges are 'ok'."""
        job = self._job()
        self.assertEqual(self._set_reading(job, 'FL', 'camber', -0.17).status, 'ok')
        self.assertEqual(self._set_reading(job, 'FL', 'caster', 6.00).status, 'ok')
        self.assertEqual(self._set_reading(job, 'FL', 'toe', 0.09).status, 'ok')

    def test_readings_out_of_spec(self):
        """TC-58: caster above 6.75 and toe above 0.17 are 'out'."""
        job = self._job()
        self.assertEqual(self._set_reading(job, 'FL', 'caster', 7.00).status, 'out')
        self.assertEqual(self._set_reading(job, 'FL', 'toe', 0.20).status, 'out')

    def test_rear_readings_use_rear_spec(self):
        """TC-59: rear camber range is -1.75 .. -0.25."""
        job = self._job()
        self.assertEqual(self._set_reading(job, 'RL', 'camber', -1.00).status, 'ok')
        self.assertEqual(self._set_reading(job, 'RL', 'camber', 0.00).status, 'out')
        self.assertEqual(self._set_reading(job, 'RL', 'toe', -0.05).status, 'ok')

    def test_known_issue_unmeasured_caster_is_out_of_spec(self):
        """TC-60 (KNOWN ISSUE D-6): an untouched reading (0) looks like a failure.

        Fix: add a 'measured' flag or treat empty readings as 'none'.
        """
        job = self._job()
        self.assertEqual(self._reading(job, 'FL', 'caster').status, 'out')

    def test_status_recomputed_when_value_changes(self):
        """TC-61: out -> ok after the value is corrected."""
        job = self._job()
        reading = self._set_reading(job, 'FL', 'caster', 7.00)
        self.assertEqual(reading.status, 'out')
        reading.write({'value': 6.00})
        self.assertEqual(reading.status, 'ok')

    def test_status_recomputed_when_spec_changes(self):
        """TC-62: changing the job spec re-evaluates every reading."""
        spec2 = self.Spec.create({'name': 'Wide caster spec', 'line_ids': [
            Command.create({'axle': 'front', 'parameter': 'caster',
                            'min_val': 0.0, 'pref_val': 5.0, 'max_val': 10.0})]})
        job = self._job()
        reading = self._reading(job, 'FL', 'caster')           # value 0
        self.assertEqual(reading.status, 'out')                # Avensis: 5.25-6.75
        job.write({'spec_id': spec2.id})
        self.assertEqual(reading.status, 'ok')                 # new spec: 0-10
        job.write({'spec_id': False})
        self.assertEqual(reading.status, 'none')

    # ==================================================================
    # H. start_alignment
    # ==================================================================
    def test_start_new_without_open_job(self):
        """TC-63: 'new' creates a measuring job with the chosen spec."""
        job_id = self.Job.start_alignment(self.vehicle.id, self.spec.id, 'new')
        job = self.Job.browse(job_id)
        self.assertEqual(job.state, 'measuring')
        self.assertEqual(job.spec_id, self.spec)
        self.assertEqual(job.vehicle_id, self.vehicle)

    def test_start_new_cancels_open_job(self):
        """TC-64: the open job is cancelled and a new one is returned."""
        old = self._job()
        job_id = self.Job.start_alignment(self.vehicle.id, self.spec.id, 'new')
        self.assertNotEqual(job_id, old.id)
        self.assertEqual(old.state, 'cancel')
        self.assertEqual(self.Job.browse(job_id).state, 'measuring')

    def test_start_continue_open_job(self):
        """TC-65: the open job is returned and gets the new spec."""
        job = self._job(spec=False)
        job_id = self.Job.start_alignment(self.vehicle.id, self.spec.id, 'continue')
        self.assertEqual(job_id, job.id)
        self.assertEqual(job.spec_id, self.spec)
        self.assertEqual(self.Job.search_count(
            [('vehicle_id', '=', self.vehicle.id)]), 1)

    def test_start_continue_keeps_existing_spec(self):
        """TC-66: no spec passed -> the job keeps its spec."""
        job = self._job()
        job_id = self.Job.start_alignment(self.vehicle.id, False, 'continue')
        self.assertEqual(job_id, job.id)
        self.assertEqual(job.spec_id, self.spec)

    def test_start_continue_without_open_job(self):
        """TC-67: no open job -> a new job is created."""
        job_id = self.Job.start_alignment(self.vehicle.id, self.spec.id, 'continue')
        job = self.Job.browse(job_id)
        self.assertEqual(job.state, 'measuring')
        self.assertEqual(self.Job.search_count(
            [('vehicle_id', '=', self.vehicle.id)]), 1)

    def test_start_does_not_touch_done_jobs(self):
        """TC-68: a done job stays done."""
        done = self._job()
        done.action_done()
        job_id = self.Job.start_alignment(self.vehicle.id, self.spec.id, 'new')
        self.assertNotEqual(job_id, done.id)
        self.assertEqual(done.state, 'done')

    def test_start_does_not_touch_other_vehicles(self):
        """TC-69: the open job of another vehicle is left alone."""
        other = self._job(vehicle=self.vehicle2)
        self.Job.start_alignment(self.vehicle.id, self.spec.id, 'new')
        self.assertEqual(other.state, 'measuring')

    def test_start_unknown_mode_acts_like_new(self):
        """TC-70: any mode other than 'continue' starts a new alignment."""
        old = self._job()
        job_id = self.Job.start_alignment(self.vehicle.id, self.spec.id, 'abc')
        self.assertNotEqual(job_id, old.id)
        self.assertEqual(old.state, 'cancel')

    def test_known_issue_continue_with_several_open_jobs(self):
        """TC-71 (KNOWN ISSUE D-7): the latest job is returned, the other stays open.

        Fix: cancel or merge the extra open jobs.
        """
        first = self._job()
        second = self._job()
        job_id = self.Job.start_alignment(self.vehicle.id, False, 'continue')
        self.assertEqual(job_id, second.id)            # highest id first (order id desc)
        self.assertEqual(first.state, 'measuring')

    # ==================================================================
    # I. Methods used by the alignment screens
    # ==================================================================
    def test_get_spec_table(self):
        """TC-72: spec header, 5 front rows, 4 rear rows, per_side flags."""
        table = self._job().get_spec_table()
        self.assertEqual(table['name'], 'TOYOTA AVENSIS 2015-2016')
        self.assertEqual(table['wheel_size'], '17"')
        self.assertEqual(len(table['front']), 5)
        self.assertEqual(len(table['rear']), 4)
        for row in table['front'] + table['rear']:
            expected = row['label'] not in ('Total Toe', 'Thrust Angle')
            self.assertEqual(row['per_side'], expected, row['label'])

    def test_get_spec_table_without_spec(self):
        """TC-73: empty table, no error."""
        table = self._job(spec=False).get_spec_table()
        self.assertEqual(table['name'], '')
        self.assertEqual(table['wheel_size'], '')
        self.assertEqual(table['front'], [])
        self.assertEqual(table['rear'], [])

    def test_get_spec_table_needs_single_job(self):
        """TC-74: ensure_one() on a recordset of 2 jobs."""
        with self.assertRaises(ValueError):
            (self._job() | self._job()).get_spec_table()

    def test_get_wheel_view_layout(self):
        """TC-75: 4 wheels in order, readings in order, job/vehicle names."""
        job = self._job()
        view = job.get_wheel_view()
        self.assertEqual([p['pos'] for p in view['positions']], POSITIONS)
        for position in view['positions']:
            params = [r['param'] for r in position['readings']]
            expected = ['camber', 'caster', 'toe'] if position['pos'][0] == 'F' \
                else ['camber', 'toe']
            self.assertEqual(params, expected)
        self.assertEqual(view['job'], job.name)
        self.assertEqual(view['vehicle'], self.vehicle.display_name)

    def test_wheel_view_summary_out(self):
        """TC-76: default readings (0) are out of spec -> summary 'out'."""
        self.assertEqual(self._job().get_wheel_view()['summary'], 'out')

    def test_wheel_view_summary_ok(self):
        """TC-77: all readings inside the spec -> summary 'ok'."""
        job = self._job()
        self._set_all_in_spec(job)
        self.assertEqual(job.get_wheel_view()['summary'], 'ok')

    def test_wheel_view_summary_nospec(self):
        """TC-78: no specification -> summary 'nospec'."""
        self.assertEqual(self._job(spec=False).get_wheel_view()['summary'], 'nospec')

    def test_wheel_view_shows_fitted_tyre(self):
        """TC-79: only the fitted position has tyre info."""
        tyre = self._tyre()
        self._fit(tyre, 'FL')
        positions = {p['pos']: p for p in self._job().get_wheel_view()['positions']}
        self.assertEqual(positions['FL']['tyre']['serial'], tyre.name)
        for pos in ('FR', 'RL', 'RR'):
            self.assertFalse(positions[pos]['tyre'])

    def test_wheel_view_ignores_scrapped_tyre(self):
        """TC-80: a scrapped tyre is not shown."""
        tyre = self._tyre()
        self._fit(tyre, 'FL')
        tyre.action_scrap()
        positions = {p['pos']: p for p in self._job().get_wheel_view()['positions']}
        self.assertFalse(positions['FL']['tyre'])

    def test_get_axle_info(self):
        """TC-81: front and rear axle info with the right wheels/readings."""
        self._fit_all()
        job = self._job()
        front = job.get_axle_info('front')
        rear = job.get_axle_info('rear')
        self.assertEqual(front['label'], 'Front axle')
        self.assertEqual([w['pos'] for w in front['wheels']], ['FL', 'FR'])
        self.assertEqual([len(w['readings']) for w in front['wheels']], [3, 3])
        self.assertEqual(rear['label'], 'Rear axle')
        self.assertEqual([w['pos'] for w in rear['wheels']], ['RL', 'RR'])
        self.assertEqual([len(w['readings']) for w in rear['wheels']], [2, 2])

    def test_get_axle_info_invalid_axle(self):
        """TC-82: an unknown axle gives label 'Rear axle' and no wheels."""
        info = self._job().get_axle_info('xyz')
        self.assertEqual(info['label'], 'Rear axle')
        self.assertEqual(info['wheels'], [])

    def test_action_done(self):
        """TC-83: measuring -> done."""
        job = self._job()
        job.action_done()
        self.assertEqual(job.state, 'done')

    def test_known_issue_done_from_cancelled_job(self):
        """TC-84 (KNOWN ISSUE D-8): a cancelled job can be marked done.

        Fix: raise UserError unless state == 'measuring'.
        """
        job = self._job()
        job.write({'state': 'cancel'})
        job.action_done()
        self.assertEqual(job.state, 'done')

    def test_action_done_several_jobs(self):
        """TC-85: action_done works on a recordset."""
        jobs = self._job() | self._job(vehicle=self.vehicle2)
        jobs.action_done()
        self.assertEqual(set(jobs.mapped('state')), {'done'})

    def test_action_open_alignment(self):
        """TC-86: returns the client action used by the JS app."""
        job = self._job()
        action = job.action_open_alignment()
        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'tyre_tracking_alignment')
        self.assertEqual(action['name'], job.name)
        self.assertEqual(action['context'], {'alignment_job_id': job.id})

    def test_action_open_alignment_needs_single_job(self):
        """TC-87: ensure_one() on a recordset of 2 jobs."""
        with self.assertRaises(ValueError):
            (self._job() | self._job()).action_open_alignment()

    # ==================================================================
    # J. Access rights
    # ==================================================================
    def _make_user(self, login, group_xmlid):
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': login, 'login': login, 'email': '%s@example.com' % login,
            'groups_id': [Command.set([self.env.ref(group_xmlid).id])]})

    def test_internal_user_has_full_access(self):
        """TC-88: an internal user can create/read/write/delete all 6 models."""
        user = self._make_user('tyre_internal', 'base.group_user')
        tyre = self._tyre()
        job = self._job()
        cases = [
            ('tyre.master', {'name': 'SEC-1'}, {'brand': 'X'}),
            ('tyre.fitment', {'tyre_id': tyre.id, 'vehicle_id': self.vehicle2.id,
                              'position': 'FL'}, {'odometer_at_fit': 1.0}),
            ('tyre.alignment.spec', {'name': 'SEC spec'}, {'wheel_size': '16"'}),
            ('tyre.alignment.spec.line', {'spec_id': self.spec.id,
                                          'parameter': 'camber'}, {'pref_val': 1.0}),
            ('tyre.alignment.job', {'vehicle_id': self.vehicle2.id}, {'state': 'done'}),
            ('tyre.alignment.reading', {'job_id': job.id, 'position': 'FL',
                                        'parameter': 'camber'}, {'value': 1.0}),
        ]
        for model, create_vals, write_vals in cases:
            with self.subTest(model=model):
                Model = self.env[model].with_user(user)
                record = Model.create(create_vals)
                self.assertTrue(record.read(['id']))
                record.write(write_vals)
                record.unlink()
                self.assertFalse(record.exists())

    def test_portal_user_has_no_access(self):
        """TC-89: a portal user cannot read the tyre models."""
        user = self._make_user('tyre_portal', 'base.group_portal')
        for model in ('tyre.master', 'tyre.alignment.job'):
            with self.subTest(model=model):
                with self.assertRaises(AccessError):
                    self.env[model].with_user(user).search([])

    # ==================================================================
    # K. Manual (browser) tests - not automated
    # ==================================================================
    # TC-90  to TC-96  : Dashboard and tyre form/list screens
    # TC-97  to TC-104 : Alignment app screens
    # Test these in the browser and fill the Excel sheet by hand.
