__author__ = 'sweemeng'
from popit.models import Organization
from popit.models import ContactDetail
from popit.models import Link
from popit.models import Identifier
from popit.models import OtherName
from popit.models import Area
from popit.models import Membership
from popit.models import Post
from popit.models import Person
from hvad.contrib.restframework import TranslatableModelSerializer
from rest_framework.serializers import CharField
from rest_framework.serializers import ValidationError
from popit.serializers.misc import OtherNameSerializer
from popit.serializers.misc import IdentifierSerializer
from popit.serializers.misc import LinkSerializer
from popit.serializers.misc import ContactDetailSerializer
from popit.serializers.misc import AreaSerializer
from popit.serializers.flat import PersonFlatSerializer
from popit.serializers.flat import PostFlatSerializer
from popit.serializers.flat import OrganizationFlatSerializer
import re


# We make this read only, and we shall show 1 level of parent. Not grand parent
class ParentOrganizationSerializer(TranslatableModelSerializer):
    id = CharField(max_length=255, required=False)
    other_names = OtherNameSerializer(many=True, required=False)
    identifiers = IdentifierSerializer(many=True, required=False)
    contact_details = ContactDetailSerializer(many=True, required=False)
    area = AreaSerializer(required=False)

    class Meta:
        model = Organization
        extra_kwargs = {'id': {'read_only': False, 'required': False}}


class OrganizationMembershipPersonSerializer(TranslatableModelSerializer):
    id = CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    birth_date = CharField(allow_null=True, default=None, allow_blank=True)
    death_date = CharField(allow_null=True, default=None, allow_blank=True)
    contact_details = ContactDetailSerializer(many=True, required=False)

    class Meta:
        model = Person
        extra_kwargs = {'id': {'read_only': False, 'required': False}}
        exclude = [ "contact_details", ]


class OrganizationMembershipSerializer(TranslatableModelSerializer):

    id = CharField(max_length=255, required=False)
    person_id = CharField(max_length=255, required=False)
    person = PersonFlatSerializer(required=False)
    organization_id = CharField(max_length=255, required=False, allow_null=True)
    organization = OrganizationFlatSerializer(required=False)
    member_id = CharField(max_length=255, required=False, allow_null=True)
    on_behalf_of_id = CharField(max_length=255, required=False, allow_null=True)
    area_id = CharField(max_length=255, required=False, allow_null=True)
    post_id = CharField(max_length=255, required=False, allow_null=True)
    post = PostFlatSerializer(required=False)

    contact_details = ContactDetailSerializer(many=True, required=False)
    links = LinkSerializer(many=True, required=False)
    start_date = CharField(allow_null=True, default=None, required=False, allow_blank=True)
    end_date = CharField(allow_null=True, default=None, required=False, allow_blank=True)

    class Meta:
        model = Membership
        extra_kwargs = {'id': {'read_only': False, 'required': False}}
        exclude = ["area"]


class OrganizationPostSerializer(TranslatableModelSerializer):

    id = CharField(max_length=255, required=False)
    other_labels = OtherNameSerializer(many=True, required=False)
    organization_id = CharField(max_length=255, required=False)
    organization = OrganizationFlatSerializer(required=False)
    area_id = CharField(max_length=255, required=False)

    contact_details = ContactDetailSerializer(many=True, required=False)
    links = LinkSerializer(many=True, required=False)
    start_date = CharField(allow_null=True, default=None)
    end_date = CharField(allow_null=True, default=None)

    class Meta:
        model = Post
        extra_kwargs = {'id': {'read_only': False, 'required': False}}
        exclude = [ "area"]


class OrganizationSerializer(TranslatableModelSerializer):

    id = CharField(max_length=255, required=False,  allow_null=True, allow_blank=True)
    parent = ParentOrganizationSerializer(required=False)
    parent_id = CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    posts = PostFlatSerializer(many=True, required=False)
    other_names = OtherNameSerializer(many=True, required=False)
    identifiers = IdentifierSerializer(many=True, required=False)
    memberships = OrganizationMembershipSerializer(many=True, required=False)
    links = LinkSerializer(many=True, required=False)
    contact_details = ContactDetailSerializer(many=True, required=False)
    area = AreaSerializer(required=False)
    area_id = CharField(max_length=255, required=False)
    founding_date = CharField(allow_null=True, default=None, allow_blank=True)
    dissolution_date = CharField(allow_null=True, default=None, required=False, allow_blank=True)

    def create(self, validated_data):
        other_names = validated_data.pop('other_names', [])
        links = validated_data.pop('links', [])
        identifiers = validated_data.pop('identifiers', [])
        contact_details = validated_data.pop('contact_details', [])
        language = self.language
        validated_data.pop("language_code", None)

        validated_data.pop("parent", None)
        validated_data.pop("memberships", None)
        validated_data.pop("posts", None)

        area_data = validated_data.pop("area", None)
        area_id = validated_data.pop("area_id", None)
        # We can only assign parent and area, not create it.
        # Except there is no area database in popit
        # Also what if area_id do not exist
        area = None
        if area_id:
            try:
                area = Area.objects.untranslated().get(id=area_id)
                validated_data["area"] = area
            except Area.DoesNotExist:
                area = None

        if area_data:
            if not area:
                area = self.create_area(area_data)
                validated_data["area"] = area


        parent_id = validated_data.pop("parent_id", None)

        if parent_id:
            parent_org = Organization.objects.untranslated().get(id=parent_id)
            validated_data["parent"] = parent_org

        # Keep elasticsearch dane as it tend to return empty string to date
        if not validated_data.get("founding_date"):
            validated_data["founding_date"] = None

        if not validated_data.get("dissolution_date"):
            validated_data["dissolution_date"] = None


        organization = Organization.objects.language(language).create(**validated_data)
        for other_name in other_names:
            self.create_child(other_name, OtherName, organization)

        for link in links:
            self.create_links(link, organization)

        for identifier in identifiers:
            self.create_child(identifier, Identifier, organization)

        for contact in contact_details:
            self.create_child(contact, ContactDetail, organization)

        return organization

    def create_links(self, validated_data, entity):
        language_code = self.language
        validated_data["content_object"] = entity
        Link.objects.language(language_code).create(**validated_data)

    def create_child(self, validated_data, child, parent):
        links = validated_data.pop("links", [])
        language_code = self.language
        validated_data["content_object"] = parent
        obj = child.objects.language(language_code).create(**validated_data)
        for link in links:
            self.create_links(link, obj)

    def create_area(self, validated_data):
        language_code = self.language
        validated_data.pop("language_code", None)
        area = Area.objects.language(language_code).create(**validated_data)
        return area

    def update(self, instance, data):
        available_languages = instance.get_available_languages()
        if not self.language in available_languages:
            instance = instance.translate(self.language)

        other_names = data.pop("other_names", [])
        links = data.pop("links", [])
        identifiers = data.pop("identifiers", [])
        contact_details = data.pop("contact_details", [])
        area = data.pop("area", None)
        area_id = data.pop("area_id", None)

        parent = data.pop("parent", None)
        parent_id = data.pop("parent_id", None)

        instance.name = data.get("name", instance.name)
        instance.classification = data.get("classification", instance.classification)
        instance.abstract = data.get("abstract", instance.abstract)
        instance.description = data.get("description", instance.description)
        instance.founding_date = data.get("founding_date", instance.founding_date)
        if not instance.founding_date:
            instance.founding_date = None
        instance.dissolution_date = data.get("dissolution_date", instance.dissolution_date)
        if not instance.dissolution_date:
            instance.dissolution_date = None

        # We only allow pointing to new parent and area not create a new parent and area
        if area_id:
            try:
                area = Area.objects.language(instance.language_code).get(id=area_id)
                instance.area = area
            except Area.DoesNotExist:
                pass

        if parent_id:
            try:
                parent = Organization.objects.language(instance.language_code).get(id=parent_id)
                instance.parent = parent
            except Organization.DoesNotExist:
                pass

        instance.save()

        for other_name in other_names:
            self.update_childs(other_name, OtherName, instance)

        for identifier in identifiers:
            self.update_childs(identifier, Identifier, instance)

        for contact in contact_details:
            self.update_childs(contact, ContactDetail, instance)

        for link in links:
            self.update_links(link, instance)

        return instance

    def update_childs(self, validated_data, child, parent):
        # parent mostly exist at create,
        language_code = parent.language_code
        if validated_data.get("id"):
            objs = child.objects.language(language_code).filter(id=validated_data.get("id"))
            if not objs:
                self.create_child(validated_data, child, parent)
            else:
                obj = objs[0]

                links = validated_data.pop("links", [])

                for key, value in validated_data.iteritems():
                    if key in ("id", "language_code", "created_at" "updated_at"):
                        continue
                    setattr(obj, key, value)

                obj.save()

                for link in links:
                    self.update_links(link, obj)
        else:
            self.create_child(validated_data, child, parent)

    def update_links(self, validated_data, parent):
        language_code = parent.language_code

        if validated_data.get("id"):
            links = Link.objects.language(language_code).filter(id=validated_data.get("id"))
            if not links:
                self.create_links(validated_data, parent)
            else:
                link = links[0]
                link.label = validated_data.get("label", link.label)
                link.field = validated_data.get("field", link.field)
                link.url = validated_data.get("url", link.url)
                link.note = validated_data.get("note", link.note)
                link.save()
        else:
            self.create_links(validated_data, parent)

    def to_representation(self, instance):
        data = super(OrganizationSerializer, self).to_representation(instance)
        # Now we do all the overriding
        if instance.parent_id:
            parent_instance = instance.parent.__class__.objects.untranslated().get(id=instance.parent_id)
            parent_serializer = ParentOrganizationSerializer(parent_instance, language=instance.language_code)
            data["parent"] = parent_serializer.data
        other_name_instance = instance.other_names.untranslated().all()
        other_name_serializer = OtherNameSerializer(instance=other_name_instance, many=True, language=instance.language_code)
        data["other_names"] = other_name_serializer.data

        identifier_instance = instance.identifiers.untranslated().all()
        identifier_serializer = IdentifierSerializer(instance=identifier_instance, many=True, language=instance.language_code)
        data["identifiers"] = identifier_serializer.data

        links_instance = instance.links.untranslated().all()
        links_serializer = LinkSerializer(instance=links_instance, many=True, language=instance.language_code)
        data["links"] = links_serializer.data

        contact_details_instance = instance.contact_details.untranslated().all()
        contact_details_serializer = ContactDetailSerializer(instance=contact_details_instance, many=True,
                                                             language=instance.language_code)
        data["contact_details"] = contact_details_serializer.data

        if instance.area_id:
            area_instance = instance.area.__class__.objects.untranslated().get(id=instance.area_id)
            area_serializer = AreaSerializer(instance, language=instance.language_code)
            data["area"] = area_serializer.data
        return data

    def validate_founding_date(self, value):
        # None is fine empty is not
        if not value:
            return value
        if not re.match(r"^[0-9]{4}(-[0-9]{2}){0,2}$", value):
            raise ValidationError("value need to be in ^[0-9]{4}(-[0-9]{2}){0,2}$ format")
        return value

    def validate_dissolution_date(self, value):
        # None is fine, empty is not
        if not value:
            return value
        if not re.match(r"^[0-9]{4}(-[0-9]{2}){0,2}$", value):
            raise ValidationError("value need to be in ^[0-9]{4}(-[0-9]{2}){0,2}$ format")
        return value

    def validate_parent_id(self, value):
        if not value:
            return value
        try:
            org = Organization.objects.untranslated().get(id=value)
        except Organization.DoesNotExist:
            raise ValidationError("Organization id %s, does not exist" % value)
        return value

    def validate_area_id(self, value):
        if not value:
            return value
        try:
            Area.objects.untranslated().get(id=value)
        except Area.DoesNotExist:
            raise ValidationError("Area id %s Does not exist" % value)
        return value

    class Meta:
        model = Organization
        extra_kwargs = {'id': {'read_only': False, 'required': False}}