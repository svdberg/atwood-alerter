-- TIME FORMATTING


module DateHelper exposing (cutOffTralingZeroes, diffDatesInDays, formatAsRssStyle)

import Date exposing (Date)
import Iso8601
import Regex
import Result exposing (Result(..))
import String
import Time exposing (Month(..), Weekday(..), Zone, toHour, toMinute, toSecond, utc)


parseIsoDate : String -> Maybe Date
parseIsoDate isoString =
    -- Truncate to first 10 characters: "YYYY-MM-DD"
    String.left 10 isoString
        |> Date.fromIsoString
        |> Result.toMaybe


parseRfcDate : String -> Maybe Date
parseRfcDate rfcString =
    -- Expecting: "Tue, 03 Jun 2025 13:46:00 +0000"
    let
        regex =
            Maybe.withDefault Regex.never <|
                Regex.fromString "(\\d{2}) (\\w{3}) (\\d{4})"

        monthStrToInt str =
            case str of
                "Jan" ->
                    Just Jan

                "Feb" ->
                    Just Feb

                "Mar" ->
                    Just Mar

                "Apr" ->
                    Just Apr

                "May" ->
                    Just May

                "Jun" ->
                    Just Jun

                "Jul" ->
                    Just Jul

                "Aug" ->
                    Just Aug

                "Sep" ->
                    Just Sep

                "Oct" ->
                    Just Oct

                "Nov" ->
                    Just Nov

                "Dec" ->
                    Just Dec

                _ ->
                    Nothing

        matches =
            Regex.find regex rfcString
    in
    case matches of
        match :: _ ->
            let
                parts =
                    match.submatches

                maybeDate =
                    case parts of
                        (Just dayStr) :: (Just monStr) :: (Just yearStr) :: _ ->
                            Maybe.map3
                                (\day month year -> Date.fromCalendarDate year month day)
                                (String.toInt dayStr)
                                (monthStrToInt monStr)
                                (String.toInt yearStr)

                        _ ->
                            Nothing
            in
            maybeDate

        _ ->
            Nothing


diffDatesInDays : String -> String -> String
diffDatesInDays isoStr rfcStr =
    let
        maybeDate1 =
            parseIsoDate isoStr

        maybeDate2 =
            parseRfcDate rfcStr
    in
    case ( maybeDate1, maybeDate2 ) of
        ( Just d1, Just d2 ) ->
            let
                diff =
                    abs (Date.diff Date.Days d2 d1)
            in
            String.fromInt diff ++ " days"

        _ ->
            "Could not parse one or both dates"


formatAsRssStyle : String -> String
formatAsRssStyle isoStr =
    case Iso8601.toTime isoStr of
        Ok posix ->
            let
                zone : Zone
                zone =
                    utc

                date : Date
                date =
                    Date.fromPosix zone posix

                hour =
                    toHour zone posix

                minute =
                    toMinute zone posix

                second =
                    toSecond zone posix

                dayOfWeek =
                    case Date.weekday date of
                        Mon ->
                            "Mon"

                        Tue ->
                            "Tue"

                        Wed ->
                            "Wed"

                        Thu ->
                            "Thu"

                        Fri ->
                            "Fri"

                        Sat ->
                            "Sat"

                        Sun ->
                            "Sun"

                month =
                    case Date.month date of
                        Jan ->
                            "Jan"

                        Feb ->
                            "Feb"

                        Mar ->
                            "Mar"

                        Apr ->
                            "Apr"

                        May ->
                            "May"

                        Jun ->
                            "Jun"

                        Jul ->
                            "Jul"

                        Aug ->
                            "Aug"

                        Sep ->
                            "Sep"

                        Oct ->
                            "Oct"

                        Nov ->
                            "Nov"

                        Dec ->
                            "Dec"

                timeStr =
                    pad2 hour ++ ":" ++ pad2 minute ++ ":" ++ pad2 second
            in
            String.join " "
                [ dayOfWeek ++ ","
                , String.fromInt (Date.day date)
                , month
                , String.fromInt (Date.year date)
                , timeStr ++ " +0000"
                ]

        Err _ ->
            isoStr


cutOffTralingZeroes : String -> String
cutOffTralingZeroes s =
    let
        suffix =
            " +0000"
    in
    if String.endsWith suffix s then
        String.dropRight (String.length suffix) s

    else
        s


pad2 : Int -> String
pad2 n =
    if n < 10 then
        "0" ++ String.fromInt n

    else
        String.fromInt n
