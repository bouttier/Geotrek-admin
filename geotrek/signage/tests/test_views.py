from collections import OrderedDict

from django.conf import settings
from django.contrib.auth.models import Permission
from django.test import TestCase

from geotrek.common.tests import CommonTest
from geotrek.authent.tests import AuthentFixturesTest
from geotrek.authent.factories import PathManagerFactory, StructureFactory
from geotrek.signage.models import Signage, Blade
from geotrek.core.factories import PathFactory
from geotrek.signage.factories import (SignageFactory, SignageTypeFactory, BladeFactory, BladeTypeFactory,
                                       SignageNoPictogramFactory, BladeDirectionFactory, BladeColorFactory,
                                       InfrastructureConditionFactory)
from geotrek.signage.filters import SignageFilterSet
from geotrek.infrastructure.tests.test_views import InfraFilterTestMixin


class SignageTest(TestCase):
    def test_helpers(self):
        p = PathFactory.create()

        self.assertEqual(len(p.signages), 0)
        if settings.TREKKING_TOPOLOGY_ENABLED:
            sign = SignageFactory.create(paths=[(p, 0.5, 0.5)])
        else:
            sign = SignageFactory.create(geom='SRID=2154;POINT (700050 6600050)')

        self.assertCountEqual(p.signages, [sign])


class BladeViewsTest(CommonTest):
    model = Blade
    modelfactory = BladeFactory
    userfactory = PathManagerFactory
    expected_json_geom = {'type': 'Point', 'coordinates': [3.0, 46.5]}

    def get_expected_json_attrs(self):
        return {
            'color': self.obj.color.pk,
            'condition': self.obj.condition.pk,
            'direction': self.obj.direction.pk,
            'number': '1',
            'order_lines': [self.obj.lines.get().pk],
            'structure': {'id': self.obj.structure.pk, 'name': 'My structure'},
            'type': {
                'label': 'Blade type'
            }
        }

    def get_bad_data(self):
        return OrderedDict([
            ('number', ''),
            ('lines-TOTAL_FORMS', '0'),
            ('lines-INITIAL_FORMS', '1'),
            ('lines-MAX_NUM_FORMS', '0'),
        ]), 'This field is required.'

    def get_good_data(self):
        good_data = {
            'number': '2',
            'type': BladeTypeFactory.create().pk,
            'condition': InfrastructureConditionFactory.create().pk,
            'direction': BladeDirectionFactory.create().pk,
            'color': BladeColorFactory.create().pk,
            'lines-TOTAL_FORMS': '2',
            'lines-INITIAL_FORMS': '0',
            'lines-MAX_NUM_FORMS': '1000',
            'lines-MIN_NUM_FORMS': '',

            'lines-0-number': "2",
            'lines-0-text': 'Text 0',
            'lines-0-distance': "10",
            'lines-0-pictogram_name': 'toto',
            'lines-0-time': '00:01:00',
            'lines-0-id': '',
            'lines-0-DELETE': '',

            'lines-1-number': "3",
            'lines-1-text': 'Text 1',
            'lines-1-distance': "0.2",
            'lines-1-pictogram_name': 'coucou',
            'lines-1-time': '00:00:10',
            'lines-1-id': '',
            'lines-1-DELETE': '',
        }
        if settings.TREKKING_TOPOLOGY_ENABLED:
            signage = SignageFactory.create()
            good_data['topology'] = '{"lat": 5.1, "lng": 6.6}'
            good_data['signage'] = signage.pk
        else:
            signage = SignageFactory.create(geom='SRID=2154;POINT(5.1 6.6)')
            good_data['signage'] = signage.pk
            good_data['topology'] = signage.geom.ewkt
        return good_data

    def _post_add_form(self):
        signa = SignageFactory.create()
        self._post_form(self._get_add_url() + '?signage=%s' % signa.pk)

    def _check_update_geom_permission(self, response):
        if self.user.has_perm('{app}.change_geom_{model}'.format(app=self.model._meta.app_label,
                                                                 model=self.model._meta.model_name)) and \
                settings.TREKKING_TOPOLOGY_ENABLED:
            self.assertContains(response, '.modifiable = true;')
        else:
            self.assertContains(response, '.modifiable = false;')

    def test_creation_form_on_signage(self):
        self.login()

        signa = SignageFactory.create()
        signage = "%s" % signa

        response = self.client.get(Blade.get_add_url() + '?signage=%s' % signa.pk)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, signage)
        form = response.context['form']
        self.assertEqual(form.initial['signage'], signa)
        # Should be able to save form successfully
        data = self.get_good_data()
        data['signage'] = signa.pk
        response = self.client.post(Blade.get_add_url() + '?signage=%s' % signa.pk, data)
        self.assertEqual(response.status_code, 302)

    def test_structure_is_set(self):
        self.login()

        signa = SignageFactory.create()

        response = self.client.post(self._get_add_url() + '?signage=%s' % signa.pk, self.get_good_data())
        self.assertEqual(response.status_code, 302)
        obj = self.model.objects.last()
        self.assertEqual(obj.structure, self.user.profile.structure)

    def test_basic_format_not_ascii(self):
        self.login()
        signage = SignageFactory.create(name="ééé")
        BladeFactory.create(signage=signage)
        for fmt in ('csv', 'shp', 'gpx'):
            response = self.client.get(self.model.get_format_list_url() + '?format=' + fmt)
            self.assertEqual(response.status_code, 200, "")

    def test_set_structure_with_permission(self):
        # The structure do not change because it changes with the signage form.
        # Need to check blade structure and line
        self.login()
        perm = Permission.objects.get(codename='can_bypass_structure')
        self.user.user_permissions.add(perm)
        structure = StructureFactory()
        self.assertNotEqual(structure, self.user.profile.structure)
        signage = SignageFactory(structure=structure)
        data = self.get_good_data()
        data['signage'] = signage.pk
        data['structure'] = self.user.profile.structure.pk
        response = self.client.post('%s?signage=%s' % (Blade.get_add_url(), signage.pk), data)
        self.assertEqual(response.status_code, 302)
        obj = self.model.objects.last()
        self.assertEqual(obj.structure, structure)
        self.logout()

    def test_structure_is_not_changed_without_permission(self):
        self.login()
        structure = StructureFactory()
        self.assertNotEqual(structure, self.user.profile.structure)
        self.assertFalse(self.user.has_perm('authent.can_bypass_structure'))
        obj = self.modelfactory.create(signage__structure=structure)
        result = self.client.post(obj.get_update_url(), self.get_good_data())
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.model.objects.first().structure, structure)
        self.logout()


class SignageViewsTest(CommonTest):
    model = Signage
    modelfactory = SignageFactory
    userfactory = PathManagerFactory
    expected_json_geom = {'type': 'Point', 'coordinates': [3.0, 46.5]}

    def get_expected_json_attrs(self):
        return {
            'code': None,
            'condition': self.obj.condition.pk,
            'manager': None,
            'name': 'Signage',
            'printed_elevation': 4807,
            'publication_date': None,
            'published': True,
            'published_status': [
                {'lang': 'en', 'language': 'English', 'status': False},
                {'lang': 'es', 'language': 'Spanish', 'status': False},
                {'lang': 'fr', 'language': 'French', 'status': False},
                {'lang': 'it', 'language': 'Italian', 'status': False}
            ],
            'sealing': self.obj.sealing.pk,
            'structure': {'id': self.obj.structure.pk, 'name': 'My structure'},
            'type': {
                'id': self.obj.type.pk,
                'label': 'Signage type',
                'pictogram': '/media/upload/signage_type.png',
            },
        }

    def get_good_data(self):
        good_data = {
            'name': 'test',
            'description': 'oh',
            'type': SignageTypeFactory.create().pk,
            'condition': InfrastructureConditionFactory.create().pk,
        }
        if settings.TREKKING_TOPOLOGY_ENABLED:
            path = PathFactory.create()
            good_data['topology'] = '{"paths": [%s]}' % path.pk
        else:
            good_data['geom'] = 'POINT(0.42 0.666)'
        return good_data

    def test_content_in_detail_page(self):
        signa = SignageFactory.create(description="<b>Beautiful !</b>")
        self.login()
        response = self.client.get(signa.get_detail_url())
        self.assertContains(response, "<b>Beautiful !</b>")
        self.assertContains(response, "(WGS 84 / Pseudo-Mercator)")

    def test_check_structure_or_none_related_are_visible(self):
        self.login()
        signagetype = SignageTypeFactory.create(structure=None)
        response = self.client.get(self.model.get_add_url())
        self.assertEqual(response.status_code, 200)
        self.assertTrue('form' in response.context)
        form = response.context['form']
        type = form.fields['type']
        self.assertTrue((signagetype.pk, str(signagetype)) in type.choices)

    def test_no_pictogram(self):
        self.login()

        self.obj = SignageNoPictogramFactory.create()
        response = self.client.get('/api/en/signages/{}'.format(self.obj.pk))
        self.assertEqual(response.status_code, 200)
        expected_json_attrs = {'id': self.obj.pk, **self.get_expected_json_attrs()}
        expected_json_attrs['type']['pictogram'] = '/static/signage/picto-signage.png'
        self.assertJSONEqual(response.content, expected_json_attrs)


class SignageFilterTest(InfraFilterTestMixin, AuthentFixturesTest):
    factory = SignageFactory
    filterset = SignageFilterSet

    def test_none_implantation_year_filter(self):

        self.login()
        model = self.factory._meta.model
        SignageFactory.create()
        response = self.client.get(model.get_list_url())
        self.assertNotContains(response, 'option value="" selected>None</option')

    def test_implantation_year_filter(self):
        filter = SignageFilterSet(data={'implantation_year': 2015})
        self.login()
        model = self.factory._meta.model
        i = SignageFactory.create(implantation_year=2015)
        i2 = SignageFactory.create(implantation_year=2016)
        response = self.client.get(model.get_list_url())

        self.assertContains(response, '<option value="2015">2015</option>')
        self.assertContains(response, '<option value="2016">2016</option>')

        self.assertTrue(i in filter.qs)
        self.assertFalse(i2 in filter.qs)

    def test_implantation_year_filter_with_str(self):
        filter = SignageFilterSet(data={'implantation_year': 'toto'})
        self.login()
        model = self.factory._meta.model
        i = SignageFactory.create(implantation_year=2015)
        i2 = SignageFactory.create(implantation_year=2016)
        response = self.client.get(model.get_list_url())

        self.assertContains(response, '<option value="2015">2015</option>')
        self.assertContains(response, '<option value="2016">2016</option>')

        self.assertIn(i, filter.qs)
        self.assertIn(i2, filter.qs)
