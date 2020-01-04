#!/bin/sh

I18NDOMAIN="listen"
LOCALES="../../../Products/listen/locales"
LOGI18NDUDE=$LOCALES/rebuild_i18n.log
EXCLUDEPOTPLONEFILE=`find ../interfaces ../browser ../lib ../utilities ../content ../extras -name "*.*py"`
MANUALPOTPLONEFILE=$LOCALES/plone-manual.pot

rm $LOGI18NDUDE

i18ndude rebuild-pot --pot $LOCALES/$I18NDOMAIN.pot --create $I18NDOMAIN ../ || exit 1
i18ndude sync --pot $LOCALES/$I18NDOMAIN.pot $LOCALES/*/LC_MESSAGES/$I18NDOMAIN.po

i18ndude rebuild-pot --pot $LOCALES/plone.pot \
    --create plone \
    --merge $MANUALPOTPLONEFILE \
    --exclude $EXCLUDEPOTPLONEFILE \
    ../profiles ../browser ../extras || exit 1
i18ndude sync --pot ./plone.pot ./*/LC_MESSAGES/plone.po

WARNINGS=`find ../ -name "*pt" | xargs i18ndude find-untranslated | grep -e '^-WARN' | wc -l`
ERRORS=`find ../ -name "*pt" | xargs i18ndude find-untranslated | grep -e '^-ERROR' | wc -l`
FATAL=`find ../ -name "*pt"  | xargs i18ndude find-untranslated | grep -e '^-FATAL' | wc -l`

echo ""
echo "There are $ERRORS errors (almost definitely missing i18n markup)"
echo "There are $WARNINGS warnings (possibly missing i18n markup)"
echo "There are $FATAL fatal errors (template could not be parsed, eg. if it's not html)"
echo ""
echo "For more details, run 'find . -name \"*pt\" | xargs i18ndude find-untranslated' or"
echo "Look the rebuild i18n log generate for this script called 'rebuild_i18n.log' on locales dir"

touch $LOGI18NDUDE

find ../ -name "*pt" | xargs i18ndude find-untranslated > $LOGI18NDUDE
