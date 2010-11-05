// An object to encapsulate our basic AJAX search functions
AJAXMemberSearch = {
    getSearchButtons: function() {
        // Returns a list of all buttons for member searches on the page
        return MochiKit.DOM.getElementsByTagAndClassName('BUTTON', 
                                                   'ajax-member-search-submit');
    },
    getClearButtons: function() {
        // Returns a list of all buttons for member searches on the page
        return MochiKit.DOM.getElementsByTagAndClassName('BUTTON', 
                                                   'ajax-member-search-reset');
    },
    getSearchButton: function(node) {
        // Returns the member search button for the current widget
        return MochiKit.DOM.getElement(this.getPrefix(node) +
                                             ".member_search_submit");
    },
    insertNewMemberFromXML: function(parent, member_elem) {
        // Create a checkbox and link for each member element retrieved
        // and add them to the specified parent element.
        var member_id = MochiKit.DOM.scrapeText(
                                     member_elem.getElementsByTagName('id')[0]);
        var member_name = MochiKit.DOM.scrapeText(
                                   member_elem.getElementsByTagName('name')[0]);
        var fullname = MochiKit.DOM.scrapeText(
                              member_elem.getElementsByTagName('fullname')[0]);
        var member_url = MochiKit.DOM.scrapeText(
                                    member_elem.getElementsByTagName('url')[0]);
        var prefix = this.getPrefix(parent);
        var input_id = prefix+'.member_'+member_id;
        //Don't add the same item twice
        if (!MochiKit.DOM.getElement(input_id)) {
            var box = MochiKit.DOM.INPUT({'type':'checkbox',
                                          'id': input_id,
                                          'name': prefix+':list',
                                          'value': member_id
                });
            var link = MochiKit.DOM.A({'href': member_url,
                                       'target': '_blank'},
                fullname+' ('+member_name+')'
                );
            var li = MochiKit.DOM.LI()
                MochiKit.DOM.appendChildNodes(li, box, link);
            MochiKit.DOM.appendChildNodes(parent, li);
        }
    },
    getPrefix: function(parent) {
        // Because there may be multiple member search widgets on a page
        // they are prefixed with a field_name to ensure id/name uniqueness.
        // Knowing that prefix is important, we obtain it by taking the entire
        // id less the portion trailing the last '.'
        var parts = parent.id.split('.');
        parts.splice(parts.length-1, 1)
        return parts.join('.');
    },
    handleMemberXML: function(node, result) {
        // Find the ul in which to insert our member objects
        // then loop through the XML member results and append
        // these to the ul
        var prefix = this.getPrefix(node)
        var parent = MochiKit.DOM.getElement(prefix +
                                             ".member_search_results");
        var elem;
        var members = MochiKit.DOM.getElementsByTagAndClassName('member',
                                                      null, result.responseXML);
        var insert = MochiKit.Base.partial(this.insertNewMemberFromXML, parent)
        // Insert each member into the container ul
        MochiKit.Iter.forEach(members, insert);
        // If there were no relevant results show a message (untranslated)
        if (MochiKit.DOM.getElementsByTagAndClassName('li', null, parent).length
            == 0) {
            MochiKit.DOM.appendChildNodes(parent,
                                          MochiKit.DOM.LI({
                                                  'id': prefix+'.no-results',},
                                                          "No results found"));
        } else if (members.length > 0) {
            //Remove the no results message
            MochiKit.DOM.removeElement(prefix+'.no-results');
        }
        //Show the containing div
        MochiKit.DOM.showElement(this.getPrefix(node)+
                                 ".search_results_container");
        // re-enable the search button once the search has finished
        this.getSearchButton(node).enabled = true;
    },
    handleMemberSearchError: function(err) {
        // Handle XML errors
        MochiKit.Logger.logError(err.message);
        // re-enable the search button once the search has finished
        this.getSearchButton(node).enabled = true;
    },
    clearResults: function(e) {
        e.preventDefault()
        e.stopPropagation()
        var node = e.src()
        var parent = MochiKit.DOM.getElement(this.getPrefix(node)+
                                             ".member_search_results");
        MochiKit.DOM.replaceChildNodes(parent) 
        //Hide the containing div
        MochiKit.DOM.hideElement(this.getPrefix(node)+
                                     ".search_results_container");
    },
    makeMemberSearchRequest: function(e) {
        // An event subscriber to make the AJAX request
        e.preventDefault()
        e.stopPropagation()
        var node = e.src()
        var prefix = this.getPrefix(node);
        var search_term = MochiKit.DOM.getElement(prefix+'.search_term');
        var search_type = MochiKit.DOM.getElement(prefix+'.search_param');
        //Remove the error class if present
        MochiKit.DOM.removeElementClass(prefix+'.search_term_field', 'error')
        if (!search_term.value) {
            //display a validation error here
            MochiKit.DOM.addElementClass(prefix+'.search_term_field', 'error')
            return;
        }
        var ajax_send = MochiKit.Async.doSimpleXMLHttpRequest(
                                             '@@member_search.html',
                                             {'search_type': search_type.value,
                                              'search_term': search_term.value}
                                                              );
        ajax_send.addCallback(this.handleMemberXML, node);
        ajax_send.addErrback(this.handleMemberSearchError);
        // disable the search button until the search has finished
        this.getSearchButton(node).enabled = false;
    },
    registerEventListeners: function() {
        //Hook up our event to the relevant buttons and initially hide the
        //results field
        var results_divs = MochiKit.DOM.getElementsByTagAndClassName('DIV',
                                                    'search-results-container');
        for (var n = 0; n < results_divs.length; n++) {
            var div = results_divs[n];
            // Hide the divs if there are no results
            if (MochiKit.DOM.getElementsByTagAndClassName('LI', null,
                                                          div).length < 1) {
                    MochiKit.DOM.hideElement(div);
            }
        }
        var search_buttons = AJAXMemberSearch.getSearchButtons();
        for (var n = 0; n < search_buttons.length; n++) {
            var button = search_buttons[n];
            MochiKit.Signal.connect(button, 'onclick', this,
                                    'makeMemberSearchRequest');
        }
        var reset_buttons = AJAXMemberSearch.getClearButtons();
        for (var n = 0; n < reset_buttons.length; n++) {
            var button = reset_buttons[n];
            MochiKit.Signal.connect(button, 'onclick', this,
                                    'clearResults');
        }
    }
}

//Ensure the object's methods have the expected value for this
MochiKit.Base.bindMethods(AJAXMemberSearch);

MochiKit.Signal.connect(window, 'onload',
                        AJAXMemberSearch.registerEventListeners);
