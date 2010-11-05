EXCLUDEPOTPLONEFILE=`find ../interfaces ../browser ../lib ../utilities ../content ../extras -name "*.*py"`
MANUALPOTPLONEFILE=../i18n/listen-plone-manual.pot

rm ./rebuild_i18n.log

i18ndude rebuild-pot --pot ./listen.pot --create listen ../ ../profiles ../browser || exit 1
i18ndude sync --pot ./listen.pot ./*/LC_MESSAGES/listen.po

i18ndude rebuild-pot --pot ../i18n/listen-plone.pot --merge $MANUALPOTPLONEFILE --exclude=$EXCLUDEPOTPLONEFILE --create plone ../profiles ../browser ../extras || exit 1
i18ndude sync --pot ../i18n/listen-plone.pot ../i18n/listen-plone-*.po

WARNINGS=`find . -name "*pt" | xargs i18ndude find-untranslated | grep -e '^-WARN' | wc -l`
ERRORS=`find . -name "*pt" | xargs i18ndude find-untranslated | grep -e '^-ERROR' | wc -l`
FATAL=`find . -name "*pt"  | xargs i18ndude find-untranslated | grep -e '^-FATAL' | wc -l`

echo
echo There are $ERRORS errors \(almost definitely missing i18n markup\)
echo There are $WARNINGS warnings \(possibly missing i18n markup\)
echo There are $FATAL fatal errors \(template could not be parsed, eg. if it\'s not html\)
echo For more details, run \'find . -name \"\*pt\" \| xargs i18ndude find-untranslated\' or 
echo Look the rebuild i18n log generate for this script called \'rebuild_i18n.log\' on locales dir 

touch ./rebuild_i18n.log

find . -name "*pt" | xargs i18ndude find-untranslated > rebuild_i18n.log

