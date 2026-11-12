module Admin exposing (main)

import AdminStats exposing (Month, Stats, barHeights, failureRate, formatLastSent, monthLabel, statsDecoder)
import Browser
import Browser.Dom
import Config exposing (apiBaseUrl)
import Html.Styled as Html exposing (Html)
import Html.Styled.Attributes as Attr
import Html.Styled.Events as Events
import Http
import Json.Encode as Encode
import Svg.Styled as Svg exposing (Svg)
import Svg.Styled.Attributes as SvgAttr
import Task



-- MODEL


type alias Model =
    { secret : String
    , loggedIn : Bool
    , loading : Bool
    , failed : Bool
    , stats : Maybe Stats
    , deleteId : String
    , confirming : Bool
    , deleteResult : Maybe (Result String String)
    }


init : () -> ( Model, Cmd Msg )
init _ =
    ( { secret = ""
      , loggedIn = False
      , loading = False
      , failed = False
      , stats = Nothing
      , deleteId = ""
      , confirming = False
      , deleteResult = Nothing
      }
    , Cmd.none
    )


type Msg
    = SecretChanged String
    | Submit
    | Refresh
    | GotStats (Result Http.Error Stats)
    | LogOut
    | DeleteIdChanged String
    | AskDelete
    | CancelDelete
    | ConfirmDelete
    | GotDelete String (Result Http.Error String)
    | Focused


fetchStats : String -> Cmd Msg
fetchStats secret =
    Http.request
        { method = "GET"
        , headers = [ Http.header "Authorization" secret ]
        , url = apiBaseUrl ++ "/admin"
        , body = Http.emptyBody
        , expect = Http.expectJson GotStats statsDecoder
        , timeout = Nothing
        , tracker = Nothing
        }


deleteEntry : String -> String -> Cmd Msg
deleteEntry secret id =
    Http.request
        { method = "DELETE"
        , headers = [ Http.header "Authorization" secret ]
        , url = apiBaseUrl ++ "/admin"
        , body =
            Http.jsonBody
                (Encode.object
                    [ ( "email", Encode.string id )
                    , ( "subscription_id", Encode.string id )
                    ]
                )
        , expect = Http.expectString (GotDelete id)
        , timeout = Nothing
        , tracker = Nothing
        }


focus : String -> Cmd Msg
focus id =
    Browser.Dom.focus id |> Task.attempt (\_ -> Focused)


errorText : Http.Error -> String
errorText err =
    case err of
        Http.BadStatus code ->
            "HTTP " ++ String.fromInt code

        Http.BadBody _ ->
            "unexpected response"

        _ ->
            "API unreachable"



-- UPDATE


update : Msg -> Model -> ( Model, Cmd Msg )
update msg model =
    case msg of
        SecretChanged s ->
            ( { model | secret = s }, Cmd.none )

        Submit ->
            if String.isEmpty model.secret || model.loading then
                ( model, Cmd.none )

            else
                ( { model | loading = True, failed = False }, fetchStats model.secret )

        Refresh ->
            ( { model | loading = True, failed = False }, fetchStats model.secret )

        GotStats (Ok stats) ->
            ( { model | loading = False, failed = False, stats = Just stats }
            , if model.loggedIn then
                Cmd.none

              else
                focus "admin-title"
            )
                |> Tuple.mapFirst (\m -> { m | loggedIn = True })

        GotStats (Err _) ->
            ( { model | loading = False, failed = True }
            , if model.loggedIn then
                Cmd.none

              else
                focus "admin-secret"
            )

        LogOut ->
            ( { model
                | secret = ""
                , loggedIn = False
                , failed = False
                , stats = Nothing
                , deleteId = ""
                , confirming = False
                , deleteResult = Nothing
              }
            , focus "admin-secret"
            )

        DeleteIdChanged s ->
            ( { model | deleteId = s, confirming = False }, Cmd.none )

        AskDelete ->
            ( { model | confirming = True, deleteResult = Nothing }, focus "delete-cancel" )

        CancelDelete ->
            ( { model | confirming = False }, focus "delete-id" )

        ConfirmDelete ->
            ( { model | confirming = False }, deleteEntry model.secret model.deleteId )

        GotDelete id result ->
            let
                outcome =
                    case result of
                        Ok _ ->
                            Ok ("Deleted " ++ id)

                        Err e ->
                            Err ("Delete failed: " ++ errorText e)
            in
            ( { model | deleteResult = Just outcome, deleteId = "", loading = True }
            , fetchStats model.secret
            )

        Focused ->
            ( model, Cmd.none )



-- COLOURS


blue : String
blue =
    "#2563eb"


emerald : String
emerald =
    "#047857"


amber : String
amber =
    "#d97706"


slate200 : String
slate200 =
    "#e2e8f0"


slate500 : String
slate500 =
    "#64748b"


slate800 : String
slate800 =
    "#1e293b"



-- VIEW


focusRing : String
focusRing =
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"


primaryButton : String
primaryButton =
    "min-h-11 px-4 rounded-lg bg-blue-600 text-white font-medium disabled:opacity-50 w-full sm:w-auto " ++ focusRing


secondaryButton : String
secondaryButton =
    "min-h-11 px-4 rounded-lg border border-slate-300 bg-white text-slate-800 font-medium disabled:opacity-50 w-full sm:w-auto " ++ focusRing


textInput : String
textInput =
    "min-h-11 w-full rounded-lg border border-slate-300 px-3 text-slate-800 " ++ focusRing


card : String
card =
    "bg-white rounded-xl shadow-md p-4 sm:p-6"


view : Model -> Html Msg
view model =
    Html.main_ [ Attr.class "min-h-screen p-4 sm:p-8 text-sm text-slate-800", Attr.style "background" "rgb(245,248,255)" ]
        [ Html.div [ Attr.class "mx-auto max-w-5xl flex flex-col gap-4" ]
            [ if model.loggedIn then
                viewDashboard model

              else
                viewLogin model
            ]
        ]


viewLogin : Model -> Html Msg
viewLogin model =
    Html.form
        [ Attr.class (card ++ " flex flex-col gap-3 max-w-md w-full mx-auto")
        , Events.onSubmit Submit
        ]
        [ Html.h1 [ Attr.class "text-xl font-bold" ] [ Html.text "Admin login" ]
        , Html.label [ Attr.for "admin-secret", Attr.class "text-slate-500" ] [ Html.text "Admin secret" ]
        , Html.input
            [ Attr.id "admin-secret"
            , Attr.type_ "password"
            , Attr.attribute "autocomplete" "current-password"
            , Attr.value model.secret
            , Events.onInput SecretChanged
            , Attr.class textInput
            ]
            []
        , if model.failed then
            Html.p [ Attr.attribute "role" "alert", Attr.class "text-red-700" ]
                [ Html.text "Login failed or API unreachable" ]

          else
            Html.text ""
        , Html.button
            [ Attr.type_ "submit"
            , Attr.disabled (String.isEmpty model.secret || model.loading)
            , Attr.class primaryButton
            ]
            [ Html.text
                (if model.loading then
                    "Logging in..."

                 else
                    "Log in"
                )
            ]
        ]


viewDashboard : Model -> Html Msg
viewDashboard model =
    let
        busy =
            model.loading
    in
    Html.div [ Attr.class "flex flex-col gap-4" ]
        [ viewHeader model
        , if model.failed then
            Html.div
                [ Attr.attribute "role" "alert"
                , Attr.class "bg-red-50 text-red-800 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-2 sm:justify-between"
                ]
                [ Html.span [] [ Html.text "Login failed or API unreachable" ]
                , Html.button [ Attr.type_ "button", Events.onClick Refresh, Attr.class secondaryButton ] [ Html.text "Try again" ]
                ]

          else
            Html.text ""
        , Html.div
            [ Attr.attribute "aria-busy"
                (if busy then
                    "true"

                 else
                    "false"
                )
            , Attr.class
                ("flex flex-col gap-4"
                    ++ (if busy && model.stats /= Nothing then
                            " opacity-60"

                        else
                            ""
                       )
                )
            ]
            (case model.stats of
                Just stats ->
                    viewStats stats

                Nothing ->
                    viewSkeleton
            )
        , viewDelete model
        ]


viewHeader : Model -> Html Msg
viewHeader model =
    Html.header [ Attr.class "flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4" ]
        [ Html.h1 [ Attr.id "admin-title", Attr.tabindex -1, Attr.class "text-2xl font-bold sm:mr-auto outline-none" ] [ Html.text "Admin" ]
        , Html.p [ Attr.class "text-slate-500" ]
            [ Html.text
                ("Last notification: "
                    ++ (model.stats
                            |> Maybe.andThen (\s -> s.notifications.lastSent)
                            |> Maybe.map formatLastSent
                            |> Maybe.withDefault "Never"
                       )
                )
            ]
        , Html.div [ Attr.class "flex flex-col sm:flex-row gap-2" ]
            [ Html.button [ Attr.type_ "button", Events.onClick Refresh, Attr.disabled model.loading, Attr.class secondaryButton ]
                [ Html.text
                    (if model.loading then
                        "Refreshing..."

                     else
                        "Refresh"
                    )
                ]
            , Html.button [ Attr.type_ "button", Events.onClick LogOut, Attr.class ("min-h-11 px-4 rounded-lg text-slate-800 underline " ++ focusRing) ] [ Html.text "Log out" ]
            ]
        ]


viewSkeleton : List (Html Msg)
viewSkeleton =
    [ Html.div [ Attr.class "grid grid-cols-2 sm:grid-cols-4 gap-4" ]
        (List.repeat 7
            (Html.div [ Attr.class "h-24 rounded-xl bg-slate-200 animate-pulse motion-reduce:animate-none" ] [])
        )
    , Html.div [ Attr.class "h-60 rounded-xl bg-slate-200 animate-pulse motion-reduce:animate-none" ] []
    ]


viewStats : Stats -> List (Html Msg)
viewStats stats =
    let
        n =
            stats.notifications

        rate =
            Maybe.map2 failureRate n.pushSuccess n.pushFailure |> Maybe.andThen identity
    in
    [ Html.dl [ Attr.class "grid grid-cols-2 sm:grid-cols-4 gap-4" ]
        [ statCard "Email confirmed" (Maybe.map String.fromInt stats.subscribers.emailConfirmed) "Unavailable right now" False
        , statCard "Email pending" (Maybe.map String.fromInt stats.subscribers.emailPending) "Unavailable right now" False
        , statCard "Web push" (Just (String.fromInt stats.subscribers.webPush)) "" False
        , statCard "Posts announced (12 mo)" (Just (String.fromInt n.postsAnnounced)) "" False
        , statCard "Emails sent (12 mo)" (Just (String.fromInt n.emailRecipients)) "" False
        , statCard "Push delivered (12 mo)" (Maybe.map String.fromInt n.pushSuccess) "Unavailable right now" False
        , statCard "Push failure rate (12 mo)"
            (Maybe.map formatPercent rate)
            (if n.pushSuccess == Nothing || n.pushFailure == Nothing then
                "Unavailable right now"

             else
                "No sends yet"
            )
            True
        ]
    , viewMix stats
    , viewMonthly stats.monthly
    ]


formatPercent : Float -> String
formatPercent r =
    let
        tenths =
            round (r * 1000)
    in
    String.fromInt (tenths // 10) ++ "." ++ String.fromInt (modBy 10 tenths) ++ "%"


statCard : String -> Maybe String -> String -> Bool -> Html Msg
statCard label value note spanRest =
    Html.div
        [ Attr.class
            ("bg-white rounded-xl shadow-md p-4"
                ++ (if spanRest then
                        " col-span-2"

                    else
                        ""
                   )
            )
        ]
        [ Html.dt [ Attr.class "text-slate-500" ] [ Html.text label ]
        , case value of
            Just v ->
                Html.dd [ Attr.class "text-[28px] leading-tight font-bold text-slate-800 tabular-nums" ] [ Html.text v ]

            Nothing ->
                Html.div []
                    [ Html.dd [ Attr.class "text-[28px] leading-tight font-bold text-slate-800", Attr.attribute "aria-label" "not available" ] [ Html.text "—" ]
                    , Html.p [ Attr.class "text-slate-500" ] [ Html.text note ]
                    ]
        ]


legendItem : String -> String -> String -> Html Msg
legendItem colour label detail =
    Html.li [ Attr.class "flex items-center gap-2" ]
        [ Html.span
            [ Attr.class "inline-block w-3 h-3 rounded-sm"
            , Attr.style "background" colour
            , Attr.style "border"
                (if colour == amber then
                    "1px solid " ++ slate800

                 else
                    "none"
                )
            ]
            []
        , Html.span [] [ Html.text (label ++ detail) ]
        ]


viewMix : Stats -> Html Msg
viewMix stats =
    let
        segments =
            List.filterMap identity
                [ Maybe.map (\v -> ( "Email confirmed", blue, v )) stats.subscribers.emailConfirmed
                , Maybe.map (\v -> ( "Email pending", amber, v )) stats.subscribers.emailPending
                , Just ( "Web push", emerald, stats.subscribers.webPush )
                ]

        total =
            List.sum (List.map (\( _, _, v ) -> v) segments)

        pct v =
            if total == 0 then
                0

            else
                round (toFloat v / toFloat total * 100)

        summary =
            segments
                |> List.map (\( l, _, v ) -> String.fromInt v ++ " " ++ String.toLower l)
                |> String.join ", "

        offsets =
            List.foldl
                (\( _, c, v ) ( acc, x ) ->
                    let
                        w =
                            if total == 0 then
                                0

                            else
                                toFloat v / toFloat total * 640
                    in
                    ( acc ++ [ ( c, x, w ) ], x + w )
                )
                ( [], 0 )
                segments
                |> Tuple.first
    in
    Html.section [ Attr.class card ]
        [ Html.h2 [ Attr.class "text-base font-semibold mb-3" ] [ Html.text "Subscriber mix" ]
        , Svg.svg
            [ Attr.attribute "role" "img"
            , Attr.attribute "aria-label" ("Subscribers: " ++ summary ++ ".")
            , SvgAttr.viewBox "0 0 640 24"
            , SvgAttr.width "100%"
            , SvgAttr.preserveAspectRatio "none"
            , Attr.style "height" "24px"
            ]
            (Svg.rect [ SvgAttr.x "0", SvgAttr.y "0", SvgAttr.width "640", SvgAttr.height "24", SvgAttr.rx "4", SvgAttr.fill slate200 ] []
                :: List.map
                    (\( c, x, w ) ->
                        Svg.rect
                            [ SvgAttr.x (String.fromFloat x)
                            , SvgAttr.y "0"
                            , SvgAttr.width (String.fromFloat w)
                            , SvgAttr.height "24"
                            , SvgAttr.fill c
                            , SvgAttr.stroke
                                (if c == amber then
                                    slate800

                                 else
                                    "none"
                                )
                            ]
                            []
                    )
                    offsets
            )
        , if total == 0 then
            Html.p [ Attr.class "mt-2 text-slate-500" ] [ Html.text "No subscribers yet" ]

          else
            Html.text ""
        , if stats.subscribers.emailConfirmed == Nothing then
            Html.p [ Attr.class "mt-2 text-slate-500" ] [ Html.text "Email counts unavailable" ]

          else
            Html.text ""
        , Html.ul [ Attr.class "mt-3 flex flex-col sm:flex-row gap-1 sm:gap-6" ]
            (List.map
                (\( l, c, v ) -> legendItem c l (": " ++ String.fromInt v ++ " (" ++ String.fromInt (pct v) ++ "%)"))
                segments
            )
        ]


viewMonthly : List Month -> Html Msg
viewMonthly months =
    let
        emails =
            List.map .emailRecipients months

        pushes =
            List.map (\m -> Maybe.withDefault 0 m.pushSuccess) months

        havePush =
            List.all (\m -> m.pushSuccess /= Nothing) months

        allZero =
            List.all (\v -> v == 0) (emails ++ pushes)

        topValue =
            if allZero then
                4

            else
                List.maximum (emails ++ pushes) |> Maybe.withDefault 4

        plotH =
            180

        left =
            44

        groupW =
            (640 - left - 6) / 12

        barW =
            18

        heights =
            barHeights plotH (topValue :: emails ++ pushes) |> List.drop 1

        ( emailHs, pushHs ) =
            ( List.take 12 heights, List.drop (List.length emails) heights )

        baseY =
            16 + plotH

        gridLine value =
            let
                y =
                    baseY - toFloat value / toFloat topValue * plotH
            in
            [ Svg.line [ SvgAttr.x1 (String.fromInt left), SvgAttr.x2 "634", SvgAttr.y1 (String.fromFloat y), SvgAttr.y2 (String.fromFloat y), SvgAttr.stroke slate200 ] []
            , Svg.text_ [ SvgAttr.x (String.fromInt (left - 6)), SvgAttr.y (String.fromFloat (y + 4)), SvgAttr.textAnchor "end", SvgAttr.fontSize "12", SvgAttr.fill slate500 ] [ Svg.text (String.fromInt value) ]
            ]

        bar x h colour label =
            Svg.rect
                [ SvgAttr.x (String.fromFloat x)
                , SvgAttr.y (String.fromFloat (baseY - h))
                , SvgAttr.width (String.fromInt barW)
                , SvgAttr.height (String.fromFloat h)
                , SvgAttr.fill colour
                ]
                [ Svg.title [] [ Svg.text label ] ]

        groups =
            List.indexedMap
                (\i m ->
                    let
                        x0 =
                            toFloat left + toFloat i * groupW + (groupW - 2 * barW) / 2

                        eh =
                            List.drop i emailHs |> List.head |> Maybe.withDefault 0

                        ph =
                            List.drop i pushHs |> List.head |> Maybe.withDefault 0

                        label =
                            monthLabel (i == 0 || String.endsWith "-01" m.month) m.month
                    in
                    Svg.g []
                        ([ bar x0 eh blue (m.month ++ " emails sent: " ++ String.fromInt m.emailRecipients) ]
                            ++ (if havePush then
                                    [ bar (x0 + barW) ph emerald (m.month ++ " push delivered: " ++ String.fromInt (Maybe.withDefault 0 m.pushSuccess)) ]

                                else
                                    []
                               )
                            ++ [ Svg.text_ [ SvgAttr.x (String.fromFloat (x0 + barW)), SvgAttr.y "234", SvgAttr.textAnchor "middle", SvgAttr.fontSize "12", SvgAttr.fill slate500 ] [ Svg.text label ] ]
                        )
                )
                months

        series name values =
            name ++ ": " ++ String.join ", " (List.map String.fromInt values)

        rangeText =
            case ( List.head months, List.reverse months |> List.head ) of
                ( Just a, Just b ) ->
                    "Monthly notifications, " ++ a.month ++ " to " ++ b.month ++ ". "

                _ ->
                    "Monthly notifications. "

        ariaLabel =
            rangeText
                ++ series "Emails sent" emails
                ++ (if havePush then
                        ". " ++ series "Push delivered" pushes

                    else
                        ". Push data unavailable"
                   )
    in
    Html.section [ Attr.class card ]
        [ Html.h2 [ Attr.class "text-base font-semibold mb-3" ] [ Html.text "Last 12 months" ]
        , Html.ul [ Attr.class "mb-2 flex flex-wrap gap-x-6 gap-y-1" ]
            (legendItem blue "Emails sent" ""
                :: (if havePush then
                        [ legendItem emerald "Push delivered" "" ]

                    else
                        []
                   )
            )
        , if havePush then
            Html.text ""

          else
            Html.p [ Attr.class "mb-2 text-slate-500" ] [ Html.text "Push data unavailable" ]
        , Html.div [ Attr.class "overflow-x-auto" ]
            [ Html.div [ Attr.class "min-w-[480px]" ]
                [ Svg.svg
                    [ Attr.attribute "role" "img"
                    , Attr.attribute "aria-label" ariaLabel
                    , SvgAttr.viewBox "0 0 640 240"
                    , SvgAttr.width "100%"
                    , SvgAttr.preserveAspectRatio "xMidYMid meet"
                    ]
                    (List.concatMap gridLine [ 0, topValue // 2, topValue ] ++ groups)
                ]
            ]
        , if allZero then
            Html.p [ Attr.class "mt-2 text-center text-slate-500" ] [ Html.text "No notifications sent in the last 12 months" ]

          else
            Html.text ""
        , Html.table [ Attr.class "sr-only" ]
            [ Html.caption [] [ Html.text "Monthly notifications" ]
            , Html.thead []
                [ Html.tr []
                    [ Html.th [] [ Html.text "Month" ]
                    , Html.th [] [ Html.text "Emails sent" ]
                    , Html.th [] [ Html.text "Push delivered" ]
                    ]
                ]
            , Html.tbody []
                (List.map
                    (\m ->
                        Html.tr []
                            [ Html.td [] [ Html.text m.month ]
                            , Html.td [] [ Html.text (String.fromInt m.emailRecipients) ]
                            , Html.td [] [ Html.text (m.pushSuccess |> Maybe.map String.fromInt |> Maybe.withDefault "not available") ]
                            ]
                    )
                    months
                )
            ]
        ]


viewDelete : Model -> Html Msg
viewDelete model =
    Html.section [ Attr.class card ]
        [ Html.h2 [ Attr.class "text-base font-semibold mb-3" ] [ Html.text "Delete subscriber" ]
        , Html.form [ Attr.class "flex flex-col gap-2", Events.onSubmit AskDelete ]
            [ Html.label [ Attr.for "delete-id", Attr.class "text-slate-500" ] [ Html.text "Email or subscription ID" ]
            , Html.div [ Attr.class "flex flex-col sm:flex-row gap-2" ]
                [ Html.input
                    [ Attr.id "delete-id"
                    , Attr.type_ "text"
                    , Attr.value model.deleteId
                    , Events.onInput DeleteIdChanged
                    , Attr.class textInput
                    ]
                    []
                , Html.button
                    [ Attr.type_ "submit"
                    , Attr.disabled (String.isEmpty (String.trim model.deleteId))
                    , Attr.class ("min-h-11 px-4 rounded-lg bg-red-600 text-white font-medium disabled:opacity-50 w-full sm:w-auto " ++ focusRing)
                    ]
                    [ Html.text "Delete" ]
                ]
            ]
        , if model.confirming then
            Html.div [ Attr.class "mt-3 flex flex-col sm:flex-row sm:items-center gap-2" ]
                [ Html.span [] [ Html.text ("Delete " ++ model.deleteId ++ "? This cannot be undone.") ]
                , Html.button [ Attr.type_ "button", Events.onClick ConfirmDelete, Attr.class ("min-h-11 px-4 rounded-lg bg-red-600 text-white font-medium " ++ focusRing) ] [ Html.text "Delete" ]
                , Html.button [ Attr.id "delete-cancel", Attr.type_ "button", Events.onClick CancelDelete, Attr.class secondaryButton ] [ Html.text "Cancel" ]
                ]

          else
            Html.text ""
        , Html.div [ Attr.attribute "role" "status", Attr.class "mt-3" ]
            [ case model.deleteResult of
                Just (Ok msg) ->
                    Html.p [ Attr.class "text-green-700" ] [ Html.text msg ]

                Just (Err msg) ->
                    Html.p [ Attr.class "text-red-700" ] [ Html.text msg ]

                Nothing ->
                    Html.text ""
            ]
        ]


main : Program () Model Msg
main =
    Browser.element
        { init = init
        , update = update
        , view = view >> Html.toUnstyled
        , subscriptions = \_ -> Sub.none
        }
