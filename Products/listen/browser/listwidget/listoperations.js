function rebuildValues(field_id) {
    var counter = 0;
    found = document.getElementById('value.'+counter+'.'+field_id);
    while (found != null) {
        found.parentNode.removeChild(found);
        counter++;
        found = document.getElementById('value.'+counter+'.'+field_id);
    }

    var selectParent = document.getElementById('select.'+field_id);
    var children = selectParent.getElementsByTagName('div'); 

    for (var x = 0; x < children.length; x++) {
        copy = document.createElement('input');
        copy.setAttribute('name', field_id);
        copy.setAttribute('type', 'hidden');
        copy.setAttribute('id', 'value.'+x+'.'+field_id);
	copy.setAttribute('value', children[x].getElementsByTagName('span')[0].innerHTML);
        selectParent.parentNode.insertBefore(copy, selectParent); 
    }
}

function sequenceAddItem(field_id) {
    var input = document.getElementById('input.'+field_id);
    if (input.value.length > 0) {

        var select = document.getElementById('select.'+field_id);
        divElement = document.createElement('div');
        divElement.setAttribute('id','select.'+input.value.length+'.'+field_id);

        labelElement = document.createElement('span'); //IE later
        labelElement.innerHTML = input.value;
        
        removeElement = document.createElement('a'); //IE later
        removeElement.setAttribute('onclick','sequenceRemoveItem(\''+field_id+'\',\''+(input.value.length)+'\'); return false;');
        removeElement.setAttribute('href','#remove');
        removeElement.setAttribute('style','text-decoration: none');
        removeElement.innerHTML = '[ - ] ';

        divElement.appendChild(removeElement);
        divElement.appendChild(labelElement);
        select.appendChild(divElement);

        rebuildValues(field_id);
    }
    input.value = '';
}

function sequenceRemoveItem(field_id, child_id) {
    var child = document.getElementById('select.'+child_id+'.'+field_id);
    child.parentNode.removeChild(child);

    rebuildValues(field_id);
    return false;
}


function onKeyPress(key) {
    if( window.event ) { // IE
	key = key.keyCode;
    } else if( key.which ) { // mozilla
	key = key.which;
    }
    if( key == 13 ) {
	sequenceAddItem('form.managers');
	return false;
    }
    return true;
}