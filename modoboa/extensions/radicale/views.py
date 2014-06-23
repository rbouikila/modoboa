"""
Radicale extension views.
"""
from itertools import chain

from django.shortcuts import render
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import (
    login_required, permission_required, user_passes_test
)
from django.utils.translation import ugettext as _

from modoboa.lib.listing import get_sort_order
from modoboa.lib.webutils import (
    _render_to_string, render_to_json_response
)
from modoboa.lib.exceptions import NotFound, PermDeniedException

from modoboa.extensions.radicale.forms import (
    UserCalendarWizard, SharedCalendarForm, UserCalendarEditionForm
)
from modoboa.extensions.radicale.models import UserCalendar, SharedCalendar


@login_required
def index(request):
    return render(request, "radicale/calendars.html", {
        "selection": "radicale"
    })


@login_required
def calendars(request, tplname="radicale/calendar_list.html"):
    """Display calendars list.

    The content depends on current user's role.
    """
    sort_order, sort_dir = get_sort_order(request.GET, "name")
    calfilter = request.GET.get("calfilter", None)
    searchquery = request.GET.get("searchquery", None)
    if request.user.group == "SimpleUsers":
        mbox = request.user.mailbox_set.all()[0]
        cals = UserCalendar.objects.filter(mailbox=mbox)
        if searchquery is not None:
            cals = cals.filter(name__icontains=searchquery)
        cals = cals.select_related().all()
        with_owner = False
    else:
        ucals = []
        if calfilter is None or calfilter == "user":
            ucals = UserCalendar.objects.get_for_admin(request.user)
            if searchquery is not None:
                ucals = ucals.filter(name__icontains=searchquery)
        scals = []
        if calfilter is None or calfilter == "shared":
            scals = SharedCalendar.objects.get_for_admin(request.user)
            if searchquery is not None:
                scals = scals.filter(name__icontains=searchquery)
        cals = chain(ucals, scals)
        with_owner = True
    cals = sorted(
        cals, key=lambda c: getattr(c, sort_order), reverse=sort_dir == '-'
    )
    return render_to_json_response({
        "table": _render_to_string(request, tplname, {
            "calendars": cals, "with_owner": with_owner
        })
    })


@login_required
def new_user_calendar(request):
    """Calendar creation view.
    """
    return UserCalendarWizard(request).process()


@login_required
def user_calendar(request, pk):
    """Edit or remove a calendar.
    """
    try:
        ucal = UserCalendar.objects.select_related().get(pk=pk)
    except UserCalendar.DoesNotExist:
        raise NotFound
    if request.user != ucal.mailbox.user and \
       not request.user.can_access(ucal.mailbox.domain):
        raise PermDeniedException
    instances = {"general": ucal, "rights": ucal}
    if request.method == "DELETE":
        ucal.delete()
        return render_to_json_response(_("Calendar removed"))
    return UserCalendarEditionForm(request, instances=instances).process()


@login_required
@permission_required("radicale.add_sharedcalendar")
def new_shared_calendar(request):
    """Shared calendar creation view.
    """
    if request.method == "POST":
        form = SharedCalendarForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            return render_to_json_response(_("Calendar created"))
        return render_to_json_response(
            {"form_errors": form.errors}, status=400
        )
    form = SharedCalendarForm(request.user)
    return render(request, "common/generic_modal_form.html", {
        "form": form,
        "formid": "sharedcal_form",
        "title": _("New shared calendar"),
        "action": reverse("new_shared_calendar"),
        "action_classes": "submit",
        "action_label": _("Submit")
    })


@login_required
@user_passes_test(
    lambda u: u.has_perm("radicale.change_sharedcalendar")
              or u.has_perm("radicale.delete_sharedcalendar")
)
def shared_calendar(request, pk):
    """Edit or remove a shared calendar.
    """
    try:
        scal = SharedCalendar.objects.select_related().get(pk=pk)
    except SharedCalendar.DoesNotExist:
        raise NotFound
    if not request.user.can_access(scal.domain):
        raise PermDeniedException
    if request.method == "DELETE":
        if not request.user.can_access(scal.domain):
            raise PermDeniedException
        scal.delete()
        return render_to_json_response(_("Calendar removed"))
    if request.method == "POST":
        form = SharedCalendarForm(request.user, request.POST, instance=scal)
        if form.is_valid():
            form.save()
            return render_to_json_response(_("Calendar updated"))
        return render_to_json_response(
            {"form_errors": form.errors}, status=400
        )
    form = SharedCalendarForm(request.user, instance=scal)
    return render(request, "common/generic_modal_form.html", {
        "form": form,
        "formid": "sharedcal_form",
        "title": scal.name,
        "action": reverse("shared_calendar", args=[scal.pk]),
        "action_classes": "submit",
        "action_label": _("Submit")
    })


@login_required
def username_list(request):
    """Get the list of username the current user can see.
    """
    from modoboa.extensions.admin.models import Domain, Mailbox

    result = []
    qset = Mailbox.objects.select_related("user")
    if request.user.has_perm("admin.add_mailbox"):
        qset = qset.filter(
            domain__in=Domain.objects.get_for_admin(request.user)
        )
    else:
        user_domain = request.user.mailbox_set.all()[0].domain
        qset = qset.filter(domain=user_domain)
    for mbox in qset:
        result.append(mbox.user.username)
    return render_to_json_response(result)
