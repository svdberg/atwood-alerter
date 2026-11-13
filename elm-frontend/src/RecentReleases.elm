module RecentReleases exposing (Release, decoder, listDecoder, statusLabel)

import DateHelper exposing (sellOutDuration)
import Json.Decode as Decode exposing (Decoder, field, string)


type alias Release =
    { title : String
    , url : String
    , published : String
    , imageUrl : String
    , sold : Bool
    , soldAt : Maybe String
    }


decoder : Decoder Release
decoder =
    Decode.map6 Release
        (field "title" string)
        (field "url" string)
        (field "published" string)
        (Decode.oneOf [ field "image_url" string, field "image_url" (Decode.null ""), Decode.succeed "" ])
        (field "sold" Decode.bool)
        (Decode.oneOf
            [ field "sold_at" (Decode.nullable string)
            , Decode.succeed Nothing
            ]
        )


listDecoder : Decoder (List Release)
listDecoder =
    Decode.oneOf
        [ field "recent_releases" (Decode.list decoder)
        , Decode.succeed []
        ]


statusLabel : Release -> String
statusLabel release =
    if not release.sold then
        "Available"

    else
        case release.soldAt |> Maybe.andThen (sellOutDuration release.published) of
            Just dur ->
                "Sold out in " ++ dur

            Nothing ->
                "Sold out"
